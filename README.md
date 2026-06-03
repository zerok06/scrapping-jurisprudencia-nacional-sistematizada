# Pipeline Industrial de Jurisprudencia del Poder Judicial del Perú

Este proyecto contiene un pipeline de datos industrial, modular, asíncrono y tolerante a fallos diseñado en Python para extraer de forma masiva y procesar la jurisprudencia de la sección **Especializada** del portal del Poder Judicial del Perú (https://jurisprudencia.pj.gob.pe/jurisprudenciaweb/).

El sistema está optimizado para operar 24/7 en servidores VPS con recursos limitados. Evita la sobrecarga de un motor de bases de datos relacionales utilizando almacenamiento indexado en archivos planos (CSV y JSON) y corpus de texto enriquecido en formato Markdown (.md) ideales para entrenamiento y RAG con Modelos de Lenguaje (LLMs).

---

## 1. Estructura del Dataset en Disco

El pipeline puebla automáticamente la siguiente estructura jerárquica de archivos y directorios:

```text
jurisprudencia_dataset/
│
├── metadata/                     # Índices y estructuras de control
│   ├── maestro_resoluciones.csv  # Relación detallada de cada UUID y resolución extraída
│   ├── arbol_conocimiento.csv    # Mapa conceptual y volumetría agregada del Derecho
│   └── temp_pages/               # JSONs temporales por página (Idempotencia y recuperación)
│       └── tmp_{especialidad}_{anio}_p{pagina}.json
│
├── cache_pdf/                    # Descargas temporales de PDFs en crudo ({uuid}.pdf)
│
└── corpus_texto/                 # Texto digitalizado en Markdown para IAs
    └── [especialidad]/           # ej: civil, penal, constitucional...
        └── [anio_resolucion]/    # ej: 2025, 2026...
            └── {uuid}.md         # Markdown con Front Matter YAML y texto limpio
```

---

## 2. Requisitos e Instalación

### Requisitos del Sistema
- Python 3.10 o superior (Probado en Python 3.12.10)
- Acceso a internet (soporta proxies configurables en `src/config.py`)
- Dependencias del sistema para OCR (en sistemas Linux sin GUI, puede requerir instalar paquetes como `libgl1-mesa-glx` y `libglib2.0-0` para OpenCV).

### Configuración del Entorno Virtual

1. **Crear e inicializar el entorno virtual**:
   ```bash
   python -m venv venv
   # En Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # En Linux / macOS:
   source venv/bin/activate
   ```

2. **Instalar dependencias de Python**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Instalar los binarios de Playwright**:
   ```bash
   playwright install chromium
   ```

---

## 3. Arquitectura del Pipeline y Comandos de Ejecución

El pipeline consta de 3 módulos desacoplados y un script consolidador independiente que pueden ejecutarse de forma secuencial o programarse como tareas (cron jobs).

### Módulo A: El Sembrador Granular (`src/seeder.py`)
Automatiza el navegador usando Playwright Headless + Stealth. Realiza búsquedas segmentadas por año y especialidad, capturando los metadatos de las tablas de RichFaces y los UUIDs de descarga de forma segura sin saturar las sesiones del servidor.

**Uso**:
```bash
# Raspado por defecto (Años 2021-2026 y todas las especialidades)
python src/seeder.py

# Raspado específico de especialidades (civil y penal) para un año determinado
python src/seeder.py -e civil,penal -y 2025

# Forzar el raspado omitiendo el mecanismo de idempotencia (sobrescribir JSONs de páginas ya existentes)
python src/seeder.py -e constitucional -y 2026 --force
```

### Módulo B: Descargador Asíncrono (`src/downloader.py`)
Lee los JSONs temporales generados por el Seeder y realiza descargas masivas en paralelo de archivos PDF utilizando `HTTPX (Async)`. Aplica límites de concurrencia y Backoff Exponencial con Jitter ante errores HTTP `429` o `503`. Valida que el archivo descargado sea un PDF válido (comprobando la firma `%PDF`) antes de guardarlo en `cache_pdf/`.

**Uso**:
```bash
# Descarga usando el límite de concurrencia predeterminado
python src/downloader.py

# Aumentar la concurrencia a 8 descargas simultáneas (máximo sugerido para evitar baneos)
python src/downloader.py -c 8
```

### Módulo C: Pipeline NLP e Hibridación (`src/nlp_pipeline.py`)
Procesa los archivos PDF guardados en la caché local. Intenta extraer texto nativo usando `pdfplumber`. Si el documento es un PDF escaneado (sin texto o muy corto), activa automáticamente el motor `PaddleOCR` (con soporte para español) para digitalizar las páginas. Sanitiza el texto y guarda el archivo Markdown `{uuid}.md` con Front Matter YAML en el directorio final, borrando el PDF original de caché para ahorrar disco.

**Uso**:
```bash
# Procesar PDFs y limpiar caché (por defecto elimina el PDF procesado)
python src/nlp_pipeline.py

# Procesar PDFs y mantener los archivos PDF en caché
python src/nlp_pipeline.py --keep-pdf
```

### Módulo de Consolidación e Indexación (`src/consolidator.py`)
Proceso periódico secundario que absorbe los metadatos JSON temporales y actualiza de manera idempotente los índices maestros:
- `maestro_resoluciones.csv`: Un registro detallado libre de duplicados de cada UUID extraído.
- `arbol_conocimiento.csv`: Agrupaciones volumétricas que detallan la cantidad de sentencias recopiladas para cada especialidad y delito/pretensión, incluyendo la lista de UUIDs correspondientes.

**Uso**:
```bash
python src/consolidator.py
```

---

## 4. Estrategias Clave de Ingeniería y Resiliencia

1. **Idempotencia Absoluta**:
   - El **Seeder** omite páginas ya raspadas si encuentra su archivo `tmp_*.json`.
   - El **Downloader** no vuelve a descargar PDFs que ya se encuentran en caché o cuya salida Markdown ya existe en la estructura final.
   - El **NLP Pipeline** no reprocesa PDFs cuyos archivos `.md` de salida estén generados.
   - El **Consolidador** realiza inserciones controladas por clave primaria (`uuid`) previniendo duplicados en el maestro.

2. **Detección Anti-Bot y WAF**:
   - Playwright utiliza `playwright-stealth` para evadir huellas de automatización.
   - HTTPX rota dinámicamente cabeceras de `User-Agent` de navegadores modernos.
   - Soporte para configurar servidores proxy de salida en `src/config.py`.

3. **Optimización de Recursos**:
   - Lazy imports en OCR: El motor OCR solo se inicializa y carga en memoria RAM si se detecta que un PDF es escaneado.
   - Liberación de disco: El pipeline elimina automáticamente los archivos PDFs de caché conforme los digitaliza exitosamente a Markdown, protegiendo el almacenamiento de VPS con discos pequeños.
