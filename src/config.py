import os
from pathlib import Path
from dotenv import load_dotenv

# ==============================================================================
# CONFIGURACIÓN DE RUTAS Y ESTRUCTURA DE DATASET
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde el archivo .env
load_dotenv(BASE_DIR / ".env")

DATASET_DIR = BASE_DIR / "jurisprudencia_dataset"

# Variable para identificar la ejecución/versión activa
ACTIVE_RUN_ID = os.getenv("ACTIVE_RUN_ID", "default").strip()
if not ACTIVE_RUN_ID:
    ACTIVE_RUN_ID = "default"

RUN_DIR = DATASET_DIR / "runs" / ACTIVE_RUN_ID

METADATA_DIR = RUN_DIR / "metadata"
CORPUS_DIR = RUN_DIR / "corpus_texto"
TEMP_PAGES_DIR = METADATA_DIR / "temp_pages"
PDF_CACHE_DIR = RUN_DIR / "cache_pdf"

# Archivos Maestros
MAESTRO_RESOLUCIONES_CSV = METADATA_DIR / "maestro_resoluciones.csv"
ARBOL_CONOCIMIENTO_CSV = METADATA_DIR / "arbol_conocimiento.csv"

# Crear directorios si no existen
for directory in [DATASET_DIR, RUN_DIR, METADATA_DIR, CORPUS_DIR, TEMP_PAGES_DIR, PDF_CACHE_DIR]:
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
anos_env = os.getenv("ANIOS")
if anos_env:
    ANOS_INTERES = [anio.strip() for anio in anos_env.split(",") if anio.strip()]
else:
    ANOS_INTERES = [str(anio) for anio in range(2021, 2027)]  # 2021 al 2026

# Nivel/Corte (1 = Corte Suprema, 2 = Corte Superior)
NIVEL_CORTE_POR_DEFECTO = "1" 

# ==============================================================================
# CONFIGURACIÓN DEL DESCARGADOR ASÍNCRONO
# ==============================================================================
DOWNLOAD_CONCURRENCY_LIMIT = int(os.getenv("DOWNLOAD_CONCURRENCY_LIMIT", "5"))  # Número máximo de descargas simultáneas (semáforo)
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

# Configuración de Proxy para Scraper
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USER = os.getenv("PROXY_USER", "").strip()
PROXY_PASS = os.getenv("PROXY_PASS", "").strip()

if PROXY_SERVER:
    if PROXY_USER and PROXY_PASS:
        if "://" in PROXY_SERVER:
            proto, host = PROXY_SERVER.split("://", 1)
            proxy_url = f"{proto}://{PROXY_USER}:{PROXY_PASS}@{host}"
        else:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_SERVER}"
    else:
        proxy_url = PROXY_SERVER
    PROXIES = [proxy_url]
else:
    PROXIES = []

# ==============================================================================
# CONFIGURACIÓN NLP & OCR
# ==============================================================================
MIN_TEXT_LENGTH_FOR_OCR = 150   # Umbral mínimo de texto para activar fallback OCR
OCR_LANGUAGE = "es"             # Idioma optimizado para PaddleOCR
DELETE_PDF_AFTER_PROCESSING = os.getenv("DELETE_PDF_AFTER_PROCESSING", "True").lower() == "true"  # True para VPS con almacenamiento limitado

# ==============================================================================
# CONFIGURACIÓN GOOGLE CLOUD STORAGE Y RASTREO
# ==============================================================================
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "").strip()
if not GCS_BUCKET_NAME:
    GCS_BUCKET_NAME = None

# Archivo PID para control del orquestador desde el dashboard
SCRAPER_PID_FILE = DATASET_DIR / "scraper.pid"

