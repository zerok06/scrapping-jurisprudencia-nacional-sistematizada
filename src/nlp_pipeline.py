import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from tqdm import tqdm

# Importar configuración y utilidades
from config import (
    TEMP_PAGES_DIR,
    PDF_CACHE_DIR,
    CORPUS_DIR,
    MIN_TEXT_LENGTH_FOR_OCR,
    OCR_LANGUAGE,
    DELETE_PDF_AFTER_PROCESSING,
    GCS_BUCKET_NAME,
    ACTIVE_RUN_ID
)
from utils import load_json, clean_yaml_field, upload_to_gcs

# Variable global para inicializar PaddleOCR de forma perezosa
OCR_ENGINE = None

def get_ocr_engine():
    """
    Inicializa de forma perezosa el motor de PaddleOCR.
    Esto evita cargar dependencias pesadas de PaddlePaddle a menos que
    se detecte un PDF escaneado que requiera OCR.
    """
    global OCR_ENGINE
    if OCR_ENGINE is not None:
        return OCR_ENGINE
        
    try:
        from paddleocr import PaddleOCR
        # Desactivar logs ruidosos de PaddleOCR para mantener limpia la consola
        OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=OCR_LANGUAGE, show_log=False)
        print("[NLP] Motor PaddleOCR inicializado con éxito para idioma:", OCR_LANGUAGE)
        return OCR_ENGINE
    except ImportError as e:
        print(f"[WARN] No se pudo cargar PaddleOCR. Asegúrese de que paddleocr y paddlepaddle estén instalados. Detalle: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Error al inicializar PaddleOCR: {e}")
        return None

def parse_arguments():
    parser = argparse.ArgumentParser(description="Pipeline NLP: Conversión de PDF a Markdown con fallback OCR")
    parser.add_argument(
        "--keep-pdf",
        action="store_true",
        help="Mantener los archivos PDF de caché después de la conversión (sobrescribe la config por defecto)"
    )
    return parser.parse_args()

def load_metadata_map() -> Dict[str, Dict[str, Any]]:
    """
    Escanea la carpeta de páginas temporales y retorna un mapa de UUID -> metadatos de resolución.
    """
    metadata_map = {}
    if not TEMP_PAGES_DIR.exists():
        return {}
        
    json_files = TEMP_PAGES_DIR.glob("tmp_*.json")
    for f in json_files:
        if "empty.json" in f.name:
            continue
        data = load_json(f)
        if data and isinstance(data, list):
            for r in data:
                uuid = r.get("uuid")
                if uuid:
                    metadata_map[uuid] = r
    return metadata_map

def extract_text_native(pdf_path: Path) -> str:
    """
    Intenta extraer el texto nativo del PDF usando pdfplumber.
    """
    import pdfplumber
    text_content = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_content.append(text)
    except Exception as e:
        print(f"[WARN] Fallo al extraer texto nativo de {pdf_path.name}: {e}")
        
    return "\n\n".join(text_content).strip()

def extract_text_ocr(pdf_path: Path) -> str:
    """
    Digitaliza el PDF página por página convirtiéndolo a imagen y aplicando PaddleOCR.
    """
    ocr = get_ocr_engine()
    if not ocr:
        print(f"[WARN] OCR no disponible. Omitiendo procesamiento OCR para {pdf_path.name}.")
        return ""

    import pdfplumber
    import numpy as np
    ocr_text_content = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for idx, page in enumerate(pdf.pages):
                # Convertir página de PDF a objeto PIL Image (150 DPI es ideal para balancear velocidad y precisión)
                try:
                    pil_img = page.to_image(resolution=150).original
                    img_array = np.array(pil_img)
                    
                    # Ejecutar OCR en la imagen
                    result = ocr.ocr(img_array, cls=True)
                    
                    # Extraer texto de forma recursiva del resultado de PaddleOCR
                    page_text = parse_paddle_result(result)
                    if page_text:
                        ocr_text_content.append(page_text)
                except Exception as ex:
                    print(f"[WARN] Error en OCR de página {idx+1} del archivo {pdf_path.name}: {ex}")
                    
    except Exception as e:
        print(f"[ERROR] Error al abrir PDF para OCR {pdf_path.name}: {e}")

    return "\n\n".join(ocr_text_content).strip()

def parse_paddle_result(ocr_result) -> str:
    """
    Recorre de forma recursiva y segura el resultado estructurado de PaddleOCR
    para reconstruir el texto completo.
    """
    if not ocr_result:
        return ""
    
    texts = []
    
    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, tuple):
            # La tupla final suele ser (texto, confianza_float)
            if len(node) == 2 and isinstance(node[0], str) and isinstance(node[1], (int, float)):
                texts.append(node[0])
            else:
                for item in node:
                    walk(item)
                    
    walk(ocr_result)
    return "\n".join(texts)

def clean_extracted_text(text: str) -> str:
    """
    Sanitiza y normaliza el texto extraído eliminando saltos de línea redundantes,
    normalizando espacios y limpiando caracteres extraños.
    """
    # Eliminar retornos de carro (\r)
    text = text.replace("\r", "")
    
    # Reemplazar múltiples saltos de línea consecutivos por un máximo de dos
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Eliminar espacios dobles o triples horizontales pero conservar saltos de línea
    lines = []
    for line in text.split("\n"):
        cleaned_line = " ".join(line.split())
        lines.append(cleaned_line)
        
    return "\n".join(lines).strip()

def build_markdown_content(metadata: Dict[str, Any], body_text: str) -> str:
    """
    Crea el archivo Markdown formateado con Front Matter YAML y el cuerpo de texto.
    """
    uuid = clean_yaml_field(metadata.get("uuid", ""))
    nro_expediente = clean_yaml_field(metadata.get("nro_expediente", ""))
    especialidad = clean_yaml_field(metadata.get("especialidad", ""))
    delito_pretension = clean_yaml_field(metadata.get("delito_pretension", ""))
    fecha = clean_yaml_field(metadata.get("fecha_resolucion", ""))
    sala_suprema = clean_yaml_field(metadata.get("sala_suprema", ""))
    tipo_resolucion = metadata.get("tipo_resolucion", "RESOLUCIÓN")
    palabras_clave = clean_yaml_field(metadata.get("palabras_clave", ""))
    
    # Limpiar posibles barras o guiones en el tipo
    tipo_resolucion = str(tipo_resolucion).strip().upper()
    
    sumilla_body = metadata.get("sumilla", "").strip()
    if not sumilla_body:
        sumilla_body = "No especificada."

    markdown_template = f"""---
uuid: "{uuid}"
nro_expediente: "{nro_expediente}"
especialidad: "{especialidad}"
delito_pretension: "{delito_pretension}"
fecha: "{fecha}"
sala_suprema: "{sala_suprema}"
tipo_resolucion: "{tipo_resolucion}"
palabras_clave: "{palabras_clave}"
---

# SENTENCIA DE {tipo_resolucion}

## RESUMEN / SUMILLA
{sumilla_body}

## TEXTO COMPLETO
{body_text}
"""
    return markdown_template

def process_pdf(pdf_path: Path, metadata: Dict[str, Any], keep_pdf: bool) -> bool:
    """
    Realiza la conversión híbrida (Nativo -> OCR) y guarda el Markdown.
    """
    uuid = metadata.get("uuid")
    especialidad = metadata.get("especialidad", "desconocido")
    fecha = metadata.get("fecha_resolucion", "")
    
    # Extraer año
    anio = "desconocido"
    if len(fecha) >= 4:
        anio = fecha[-4:]
        if not anio.isdigit():
            match = re.search(r"\b(19\d{2}|20\d{2})\b", fecha)
            if match:
                anio = match.group(1)

    # Definir ruta destino
    target_dir = CORPUS_DIR / especialidad / anio
    target_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = target_dir / f"{uuid}.md"

    # 1. Extracción Nativa
    text = extract_text_native(pdf_path)
    extraction_method = "nativo"

    # 2. Comprobar si requiere OCR
    if len(text) < MIN_TEXT_LENGTH_FOR_OCR:
        # print(f"\n[NLP] Texto nativo insuficiente ({len(text)} caracteres) para {uuid}. Activando fallback OCR...")
        text = extract_text_ocr(pdf_path)
        extraction_method = "ocr"

    if not text:
        # print(f"[ERROR] No se pudo extraer texto de ninguna forma para {uuid}.")
        return False

    # 3. Limpiar texto
    cleaned_text = clean_extracted_text(text)

    # 4. Construir contenido de Markdown
    markdown_content = build_markdown_content(metadata, cleaned_text)

    # 5. Guardar en disco
    try:
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        # Subir a GCS si está configurado
        if GCS_BUCKET_NAME:
            gcs_path = f"runs/{ACTIVE_RUN_ID}/corpus_texto/{especialidad}/{anio}/{uuid}.md"
            upload_to_gcs(markdown_path, GCS_BUCKET_NAME, gcs_path)
            
        # 6. Eliminar PDF si está configurado
        if not keep_pdf:
            pdf_path.unlink()
            
        return True
    except Exception as e:
        print(f"[ERROR] Error al guardar Markdown {markdown_path.name}: {e}")
        return False

def main():
    args = parse_arguments()
    keep_pdf = args.keep_pdf or not DELETE_PDF_AFTER_PROCESSING

    print("======================================================================")
    print("INICIANDO CONVERSOR Y PIPELINE NLP (MÓDULO C)")
    print(f"Conservar archivos PDF en caché: {keep_pdf}")
    print("======================================================================")

    # Cargar mapa de metadatos recopilados por el Seeder
    metadata_map = load_metadata_map()
    if not metadata_map:
        print("[NLP] No se encontraron metadatos en temp_pages/. Ejecute el Seeder primero.")
        return

    # Escanear PDFs descargados en la carpeta de caché
    if not PDF_CACHE_DIR.exists():
        print(f"[NLP] El directorio de caché de PDF {PDF_CACHE_DIR} no existe.")
        return

    pdf_files = list(PDF_CACHE_DIR.glob("*.pdf"))
    print(f"[NLP] Se encontraron {len(pdf_files)} archivos PDF en la caché local.")

    if not pdf_files:
        print("[NLP] No hay archivos PDF pendientes de procesar en la caché.")
        return

    processed_count = 0
    failed_count = 0

    # Iterar y procesar con barra de progreso
    for pdf_path in tqdm(pdf_files, desc="Procesando PDFs a Markdown"):
        uuid = pdf_path.stem  # El nombre del archivo es el UUID
        metadata = metadata_map.get(uuid)
        
        if not metadata:
            # Intentar crear un metadato mínimo si el PDF existe pero no está en el mapa
            metadata = {
                "uuid": uuid,
                "nro_expediente": "desconocido",
                "especialidad": "desconocido",
                "delito_pretension": "desconocido",
                "fecha_resolucion": "01/01/2000",
                "tipo_resolucion": "RESOLUCION"
            }

        success = process_pdf(pdf_path, metadata, keep_pdf)
        if success:
            processed_count += 1
        else:
            failed_count += 1

    print("\n======================================================================")
    print("RESUMEN DE PROCESAMIENTO NLP (MÓDULO C)")
    print(f"Convertidos exitosamente: {processed_count}")
    print(f"Fallidos: {failed_count}")
    print("======================================================================")

if __name__ == "__main__":
    main()
