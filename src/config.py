import os
from pathlib import Path

# ==============================================================================
# CONFIGURACIÓN DE RUTAS Y ESTRUCTURA DE DATASET
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "jurisprudencia_dataset"

METADATA_DIR = DATASET_DIR / "metadata"
CORPUS_DIR = DATASET_DIR / "corpus_texto"
TEMP_PAGES_DIR = METADATA_DIR / "temp_pages"
PDF_CACHE_DIR = DATASET_DIR / "cache_pdf"

# Archivos Maestros
MAESTRO_RESOLUCIONES_CSV = METADATA_DIR / "maestro_resoluciones.csv"
ARBOL_CONOCIMIENTO_CSV = METADATA_DIR / "arbol_conocimiento.csv"

# Crear directorios si no existen
for directory in [DATASET_DIR, METADATA_DIR, CORPUS_DIR, TEMP_PAGES_DIR, PDF_CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# CONFIGURACIÓN DEL PORTAL JURISPRUDENCIA
# ==============================================================================
PORTAL_URL = "https://jurisprudencia.pj.gob.pe/jurisprudenciaweb/faces/page/inicio.xhtml"

# Mapeo de Especialidades (Valores de las opciones en el <select> de RichFaces)
ESPECIALIDADES = {
    "civil": "1",
    "comercial": "2",
    "constitucional": "12",
    "contencioso_adm_laboral": "7",
    "contencioso_adm_previsional": "8",
    "contencioso_administrativo": "3",
    "familia_civil": "4",
    "familia_penal": "6",
    "familia_tutelar": "5",
    "laboral": "9",
    "penal": "10",
    "revision_coactivo": "11",
}

# Rango de años de interés
ANOS_INTERES = [str(anio) for anio in range(2021, 2027)]  # 2021 al 2026

# Nivel/Corte (1 = Corte Suprema, 2 = Corte Superior)
NIVEL_CORTE_POR_DEFECTO = "1" 

# ==============================================================================
# CONFIGURACIÓN DEL DESCARGADOR ASÍNCRONO
# ==============================================================================
DOWNLOAD_CONCURRENCY_LIMIT = 5  # Número máximo de descargas simultáneas (semáforo)
DOWNLOAD_TIMEOUT = 30.0         # Timeout de petición HTTP en segundos
DOWNLOAD_MAX_RETRIES = 5        # Intentos máximos por archivo
DOWNLOAD_BACKOFF_FACTOR = 2.0   # Factor exponencial (2s, 4s, 8s, 16s...)
DOWNLOAD_BACKOFF_MAX = 60.0     # Retardo máximo de backoff

# Rotación de User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# Lista de proxies (Si está vacía, no se utilizarán proxies. Formato: {"http://": "...", "https://": "..."})
PROXIES = []  # Ejemplo: [{"http://": "http://user:pass@ip:port", "https://": "http://user:pass@ip:port"}]

# ==============================================================================
# CONFIGURACIÓN NLP & OCR
# ==============================================================================
MIN_TEXT_LENGTH_FOR_OCR = 150   # Umbral mínimo de texto para activar fallback OCR
OCR_LANGUAGE = "es"             # Idioma optimizado para PaddleOCR
DELETE_PDF_AFTER_PROCESSING = True  # True para VPS con almacenamiento limitado
