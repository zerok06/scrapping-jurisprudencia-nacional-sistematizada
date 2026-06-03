import asyncio
import argparse
import random
import sys
from pathlib import Path
from typing import Dict, List, Set, Any
import httpx
from tqdm.asyncio import tqdm

# Importar configuración y utilidades
from config import (
    TEMP_PAGES_DIR,
    PDF_CACHE_DIR,
    CORPUS_DIR,
    DOWNLOAD_CONCURRENCY_LIMIT,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_MAX_RETRIES,
    DOWNLOAD_BACKOFF_FACTOR,
    DOWNLOAD_BACKOFF_MAX,
    USER_AGENTS,
    PROXIES
)
from utils import load_json

def parse_arguments():
    parser = argparse.ArgumentParser(description="Descargador Asíncrono de Jurisprudencia por UUID")
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=DOWNLOAD_CONCURRENCY_LIMIT,
        help=f"Límite de descargas simultáneas (por defecto: {DOWNLOAD_CONCURRENCY_LIMIT})"
    )
    return parser.parse_args()

def collect_records() -> List[Dict[str, Any]]:
    """
    Escanea la carpeta de páginas temporales y recopila todos los registros únicos.
    """
    records: Dict[str, Dict[str, Any]] = {}
    if not TEMP_PAGES_DIR.exists():
        print(f"[WARN] El directorio temporal {TEMP_PAGES_DIR} no existe.")
        return []

    json_files = list(TEMP_PAGES_DIR.glob("tmp_*.json"))
    print(f"[DOWNLOADER] Escaneando {len(json_files)} archivos JSON temporales...")

    for f in json_files:
        # Ignorar archivos marcados como vacíos
        if "empty.json" in f.name:
            continue
        data = load_json(f)
        if data and isinstance(data, list):
            for r in data:
                uuid = r.get("uuid")
                if uuid:
                    # Guardamos el registro, evitando duplicados
                    records[uuid] = r

    return list(records.values())

def get_markdown_path(record: Dict[str, Any]) -> Path:
    """
    Construye la ruta esperada del archivo Markdown final.
    """
    especialidad = record.get("especialidad", "desconocido")
    fecha = record.get("fecha_resolucion", "")
    
    # Extraer año de la fecha (formato esperado: DD/MM/YYYY)
    anio = "desconocido"
    if len(fecha) >= 4:
        anio = fecha[-4:]
        if not anio.isdigit():
            # Intentar extraer cualquier número de 4 dígitos
            import re
            match = re.search(r"\b(19\d{2}|20\d{2})\b", fecha)
            if match:
                anio = match.group(1)

    uuid = record.get("uuid")
    return CORPUS_DIR / especialidad / anio / f"{uuid}.md"

async def download_file(
    client: httpx.AsyncClient,
    uuid: str,
    pdf_path: Path,
    semaphore: asyncio.Semaphore
) -> bool:
    """
    Descarga un PDF usando HTTPX con reintentos y Backoff Exponencial.
    """
    url = f"https://jurisprudencia.pj.gob.pe/jurisprudenciaweb/ServletDescarga?uuid={uuid}"
    
    # Intentos de descarga
    for attempt in range(1, DOWNLOAD_MAX_RETRIES + 1):
        async with semaphore:
            try:
                # Seleccionar un User-Agent aleatorio para cada intento
                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                    "Connection": "keep-alive"
                }

                response = await client.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT)
                
                # Comprobar el código de respuesta
                if response.status_code == 200:
                    content = response.content
                    
                    # Validar que los bytes descargados correspondan a un PDF válido (Firma %PDF)
                    if content.startswith(b"%PDF"):
                        # Escribir el PDF a disco
                        with open(pdf_path, "wb") as f:
                            f.write(content)
                        return True
                    else:
                        # La respuesta no es un PDF (podría ser un captcha, error JSF, sesión expirada, etc.)
                        error_snippet = content[:200].decode("utf-8-sig", errors="ignore")
                        raise ValueError(f"El servidor no devolvió un PDF válido. Inicio de respuesta: '{error_snippet.strip()}'")
                
                elif response.status_code in [429, 503]:
                    # Servidor saturado o bloqueando peticiones temporalmente
                    raise httpx.HTTPStatusError(
                        f"Status {response.status_code} (Rate Limiting/Service Unavailable)",
                        request=response.request,
                        response=response
                    )
                else:
                    # Otro tipo de error HTTP no recuperable
                    response.raise_for_status()

            except Exception as e:
                # Si es el último intento, propagar el fallo
                if attempt == DOWNLOAD_MAX_RETRIES:
                    # print(f"\n[ERROR] Falló la descarga de {uuid} tras {DOWNLOAD_MAX_RETRIES} intentos: {e}")
                    return False
                
                # Calcular delay exponencial con un componente aleatorio (Jitter) para evitar colisiones
                delay = min(DOWNLOAD_BACKOFF_MAX, (DOWNLOAD_BACKOFF_FACTOR ** attempt) + random.uniform(0.5, 1.5))
                # Silencioso en el progreso normal para no ensuciar la barra de progreso
                await asyncio.sleep(delay)
                
    return False

async def main_downloader(concurrency: int):
    # Recopilar todos los registros de los JSON temporales
    all_records = collect_records()
    if not all_records:
        print("[DOWNLOADER] No se encontraron registros para descargar. Asegúrate de ejecutar el Seeder primero.")
        return

    print(f"[DOWNLOADER] Total de registros cargados: {len(all_records)}")

    # Filtrar registros que ya han sido descargados o procesados
    pending_records = []
    for r in all_records:
        uuid = r.get("uuid")
        pdf_path = PDF_CACHE_DIR / f"{uuid}.pdf"
        md_path = get_markdown_path(r)
        
        # Saltarse si ya se generó el Markdown final o si ya tenemos el PDF en caché
        if md_path.exists():
            continue
        if pdf_path.exists():
            continue
            
        pending_records.append(r)

    total_pending = len(pending_records)
    print(f"[DOWNLOADER] Registros pendientes de descarga: {total_pending} / {len(all_records)}")

    if total_pending == 0:
        print("[DOWNLOADER] Todos los documentos ya están descargados o convertidos. Nada que hacer.")
        return

    # Configurar cliente HTTPX con proxies si están definidos
    proxy_config = PROXIES[0] if PROXIES else None
    
    # Crear semáforo para limitar la concurrencia
    semaphore = asyncio.Semaphore(concurrency)
    
    # Iniciar cliente asíncrono
    async with httpx.AsyncClient(proxy=proxy_config, verify=True) as client:
        # Envolver tareas
        tasks = []
        for r in pending_records:
            uuid = r.get("uuid")
            pdf_path = PDF_CACHE_DIR / f"{uuid}.pdf"
            tasks.append(download_file(client, uuid, pdf_path, semaphore))
            
        # Ejecutar con barra de progreso
        print(f"[DOWNLOADER] Iniciando descarga masiva con concurrencia={concurrency}...")
        results = await tqdm.gather(*tasks, desc="Descargando jurisprudencia")
        
        successful_downloads = sum(1 for res in results if res)
        failed_downloads = total_pending - successful_downloads
        
        print("\n======================================================================")
        print("RESUMEN DE DESCARGAS (MÓDULO B)")
        print(f"Total procesados: {total_pending}")
        print(f"Descargas exitosas: {successful_downloads}")
        print(f"Descargas fallidas: {failed_downloads}")
        print("======================================================================")

if __name__ == "__main__":
    args = parse_arguments()
    asyncio.run(main_downloader(args.concurrency))
