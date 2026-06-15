import argparse
import re
from pathlib import Path
from typing import Dict, List, Set, Any

# Importar configuración y utilidades
from config import (
    TEMP_PAGES_DIR,
    MAESTRO_RESOLUCIONES_CSV,
    ARBOL_CONOCIMIENTO_CSV,
    GCS_BUCKET_NAME,
    ACTIVE_RUN_ID
)
from utils import (
    load_json,
    read_csv_records,
    append_csv_records,
    write_csv_records,
    clean_string,
    upload_to_gcs
)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Consolidador del Dataset: Maestro e Índice de Volumetría")
    return parser.parse_args()

def slugify(text: str) -> str:
    """
    Normaliza y convierte un texto en un identificador único tipo slug legible.
    """
    text = text.lower().strip()
    # Reemplazar vocales acentuadas
    text = re.sub(r"[áàäâ]", "a", text)
    text = re.sub(r"[éèëê]", "e", text)
    text = re.sub(r"[íìïî]", "i", text)
    text = re.sub(r"[óòöô]", "o", text)
    text = re.sub(r"[úùüû]", "u", text)
    text = re.sub(r"[ñ]", "n", text)
    # Remover caracteres no alfanuméricos
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    # Reemplazar espacios y guiones múltiples por guión bajo
    text = re.sub(r"[\s-]+", "_", text)
    return text.strip("_")

def collect_temp_records() -> List[Dict[str, Any]]:
    """
    Carga todos los registros de los archivos JSON de páginas temporales.
    """
    records = []
    if not TEMP_PAGES_DIR.exists():
        return []

    json_files = TEMP_PAGES_DIR.glob("tmp_*.json")
    for f in json_files:
        if "empty.json" in f.name:
            continue
        data = load_json(f)
        if data and isinstance(data, list):
            for r in data:
                uuid = r.get("uuid")
                if uuid:
                    records.append(r)
    return records

def build_maestro_record(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye la fila para el CSV maestro con todas las columnas requeridas.
    """
    uuid = r.get("uuid", "")
    especialidad = r.get("especialidad", "desconocido")
    fecha = r.get("fecha_resolucion", "")
    
    # Extraer año de resolución
    anio = "desconocido"
    if len(fecha) >= 4:
        anio = fecha[-4:]
        if not anio.isdigit():
            match = re.search(r"\b(19\d{2}|20\d{2})\b", fecha)
            if match:
                anio = match.group(1)

    ruta_markdown = f"corpus_texto/{especialidad}/{anio}/{uuid}.md"

    return {
        "uuid": uuid,
        "nro_expediente": r.get("nro_expediente", ""),
        "tipo_resolucion": r.get("tipo_resolucion", ""),
        "fecha_resolucion": fecha,
        "sala_suprema": r.get("sala_suprema", ""),
        "especialidad": especialidad,
        "delito_pretension": r.get("delito_pretension", ""),
        "ruta_markdown": ruta_markdown
    }

def main():
    args = parse_arguments()
    
    print("======================================================================")
    print("INICIANDO CONSOLIDACIÓN E INDEXACIÓN")
    print("======================================================================")

    # 1. Recopilar registros de páginas temporales
    temp_records = collect_temp_records()
    print(f"[CONSOLIDATOR] Registros leídos de archivos temporales: {len(temp_records)}")

    if not temp_records:
        print("[CONSOLIDATOR] No hay archivos JSON temporales para procesar. El maestro se actualizará a partir de los datos existentes.")

    # 2. Convertir registros al formato del CSV maestro
    maestro_records_to_append = [build_maestro_record(r) for r in temp_records]

    # Columnas requeridas del maestro
    maestro_fields = [
        "uuid",
        "nro_expediente",
        "tipo_resolucion",
        "fecha_resolucion",
        "sala_suprema",
        "especialidad",
        "delito_pretension",
        "ruta_markdown"
    ]

    # Agregar de forma idempotente (libre de duplicados por uuid) al CSV maestro
    new_inserts = append_csv_records(
        MAESTRO_RESOLUCIONES_CSV,
        fieldnames=maestro_fields,
        records=maestro_records_to_append,
        key_field="uuid"
    )
    print(f"[CONSOLIDATOR] Nuevos registros agregados a 'maestro_resoluciones.csv': {new_inserts}")
    
    # Subir maestro de resoluciones a GCS
    if GCS_BUCKET_NAME and MAESTRO_RESOLUCIONES_CSV.exists():
        upload_to_gcs(MAESTRO_RESOLUCIONES_CSV, GCS_BUCKET_NAME, f"runs/{ACTIVE_RUN_ID}/metadata/maestro_resoluciones.csv")

    # 3. Leer el maestro completo para reconstruir el árbol de conocimiento
    full_maestro_records = read_csv_records(MAESTRO_RESOLUCIONES_CSV)
    print(f"[CONSOLIDATOR] Total de registros actuales en el índice maestro: {len(full_maestro_records)}")

    if not full_maestro_records:
        print("[CONSOLIDATOR] No hay registros en el maestro para calcular el árbol de conocimiento. Fin.")
        return

    # 4. Agrupar volumetría por Especialidad y Delito/Pretensión para construir el árbol de conocimiento
    # Clave de agrupación: (nivel_1_especialidad, nivel_2_delito_pretension)
    groups: Dict[tuple, List[str]] = {}

    for r in full_maestro_records:
        esp = clean_string(r.get("especialidad", "desconocido"))
        delito = clean_string(r.get("delito_pretension", "no_especificado"))
        if not delito:
            delito = "no_especificado"
            
        key = (esp, delito)
        if key not in groups:
            groups[key] = []
            
        uuid = r.get("uuid")
        if uuid:
            groups[key].append(uuid)

    # 5. Escribir arbol_conocimiento.csv
    knowledge_tree_records = []
    
    for (esp, delito), uuids in groups.items():
        # Generar categoría única legibles
        categoria_id = f"{slugify(esp)}_{slugify(delito)}"
        
        knowledge_tree_records.append({
            "categoria_id": categoria_id,
            "nivel_1_especialidad": esp,
            "nivel_2_delito_pretension": delito,
            "cantidad_documentos": len(uuids),
            "lista_uuids": ";".join(uuids)
        })

    # Ordenar por especialidad y luego por volumen descendente para scannability
    knowledge_tree_records.sort(key=lambda x: (x["nivel_1_especialidad"], -x["cantidad_documentos"]))

    arbol_fields = [
        "categoria_id",
        "nivel_1_especialidad",
        "nivel_2_delito_pretension",
        "cantidad_documentos",
        "lista_uuids"
    ]

    success = write_csv_records(ARBOL_CONOCIMIENTO_CSV, fieldnames=arbol_fields, records=knowledge_tree_records)
    
    if success:
        print(f"[CONSOLIDATOR] Árbol de conocimiento actualizado con éxito en '{ARBOL_CONOCIMIENTO_CSV.name}'.")
        print(f"[CONSOLIDATOR] Total de categorías conceptuales creadas: {len(knowledge_tree_records)}")
        
        # Subir árbol de conocimiento a GCS
        if GCS_BUCKET_NAME:
            upload_to_gcs(ARBOL_CONOCIMIENTO_CSV, GCS_BUCKET_NAME, f"runs/{ACTIVE_RUN_ID}/metadata/arbol_conocimiento.csv")
    else:
        print("[ERROR] Fallo al escribir el árbol de conocimiento.")

    print("======================================================================")
    print("CONSOLIDACIÓN COMPLETA")
    print("======================================================================")

if __name__ == "__main__":
    main()
