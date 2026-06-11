import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import sys
import os
import time
from pathlib import Path
from datetime import datetime, date

# Importar configuración y utilidades
import config
from utils import (
    get_running_scraper_pid,
    kill_scraper_process,
    list_gcs_runs,
    download_from_gcs
)

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Jurisprudencia Nacional Sistematizada",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyectar estilos CSS para el diseño Premium (Dark Mode con Glassmorphism y detalles cian/azul)
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<style>
    /* Estilos generales y tipografía */
    html, body, [class*="css"], .stText, p, span, h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif !important;
    }
    
    /* Fondo principal con degradado sutil */
    .stApp {
        background: radial-gradient(circle at top right, #0d1527 0%, #070a13 100%);
        color: #e2e8f0;
    }
    
    /* Barra lateral */
    section[data-testid="stSidebar"] {
        background-color: #0b0f19 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Encabezado principal */
    .main-title {
        background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin-bottom: 0.1rem;
        letter-spacing: -0.5px;
    }
    
    .subtitle {
        color: #94a3b8;
        font-size: 1.15rem;
        font-weight: 400;
        margin-bottom: 1.8rem;
    }
    
    /* Tarjetas de métricas (Glassmorphism) */
    .metric-card {
        background: rgba(15, 23, 42, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.25rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        text-align: center;
    }
    
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(56, 189, 248, 0.4);
        box-shadow: 0 12px 40px 0 rgba(56, 189, 248, 0.15);
    }
    
    .metric-val {
        font-size: 2.3rem;
        font-weight: 800;
        color: #38bdf8;
        margin: 0.4rem 0;
        letter-spacing: -1px;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.2px;
    }
    
    /* Divisor estilizado */
    .gradient-divider {
        height: 2px;
        background: linear-gradient(90deg, #38bdf8, #818cf8, transparent);
        margin: 1.8rem 0;
    }
    
    /* Contenedor del visualizador de documentos markdown */
    .document-box {
        background-color: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 1.5rem;
        max-height: 500px;
        overflow-y: auto;
        color: #e2e8f0;
        line-height: 1.6;
    }
    
    /* Ficha técnica */
    .ficha-tecnica {
        background: rgba(30, 41, 59, 0.25);
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid rgba(255, 255, 255, 0.04);
    }
    
    /* Consola de logs en vivo */
    .log-console {
        background-color: #020617;
        color: #34d399;
        font-family: 'Fira Code', 'Courier New', monospace !important;
        padding: 1.2rem;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        font-size: 0.85rem;
        line-height: 1.45;
        max-height: 380px;
        overflow-y: auto;
        white-space: pre-wrap;
        box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.8);
    }
    
    /* Botones de control */
    div.stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    
    /* Status Badge */
    .status-badge {
        display: inline-block;
        padding: 0.4rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        margin-bottom: 1rem;
    }
    
    .status-active {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    
    .status-stopped {
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# FUNCIONES DE DATOS Y CONTEO (Dinámicas usando referencias a config.*)
# ==============================================================================
@st.cache_data(ttl=3)
def load_maestro_data():
    if not config.MAESTRO_RESOLUCIONES_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(config.MAESTRO_RESOLUCIONES_CSV)
        df['uuid'] = df['uuid'].astype(str)
        return df
    except Exception as e:
        st.error(f"Error al leer maestro_resoluciones.csv: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3)
def load_arbol_data():
    if not config.ARBOL_CONOCIMIENTO_CSV.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(config.ARBOL_CONOCIMIENTO_CSV)
    except Exception as e:
        st.error(f"Error al leer arbol_conocimiento.csv: {e}")
        return pd.DataFrame()

def count_temp_pages():
    if not config.TEMP_PAGES_DIR.exists():
        return 0
    return len(list(config.TEMP_PAGES_DIR.glob("tmp_*.json")))

def count_cached_pdfs():
    if not config.PDF_CACHE_DIR.exists():
        return 0
    return len(list(config.PDF_CACHE_DIR.glob("*.pdf")))

def count_corpus_markdowns():
    if not config.CORPUS_DIR.exists():
        return 0
    return len(list(config.CORPUS_DIR.glob("**/*.md")))

# ==============================================================================
# OBTENCIÓN Y GESTIÓN DE VERSIONES (RUNS)
# ==============================================================================
def get_all_runs():
    """
    Lista todos los IDs de ejecuciones encontradas tanto localmente como en GCS.
    """
    runs = set()
    
    # 1. Escaneo de carpetas locales
    runs_dir = config.DATASET_DIR / "runs"
    if runs_dir.exists():
        for d in runs_dir.iterdir():
            if d.is_dir() and d.name.startswith("run_"):
                runs.add(d.name)
                
    # 2. Escaneo de prefijos en GCS
    if config.GCS_BUCKET_NAME:
        gcs_runs = list_gcs_runs(config.GCS_BUCKET_NAME)
        for r in gcs_runs:
            runs.add(r)
            
    # Convertir a lista ordenada descendentemente (los más nuevos primero)
    sorted_runs = sorted(list(runs), reverse=True)
    if not sorted_runs:
        sorted_runs = ["default"]
        
    return sorted_runs

# ==============================================================================
# GESTIÓN DEL SUBPROCESO DEL SCRAPER
# ==============================================================================
def start_scraper_subprocess(mode="once", interval=12.0, specialties="", start_date="", end_date="", active_run_id=""):
    """
    Inicia el orquestador principal (main.py) en un proceso de segundo plano.
    Pasa la variable de entorno ACTIVE_RUN_ID para guardar los datos en esa versión.
    """
    script_path = config.BASE_DIR / "src" / "main.py"
    
    cmd = [sys.executable, str(script_path)]
    if mode == "once":
        cmd += ["--once"]
    else:
        cmd += ["-i", str(interval)]
        
    if specialties:
        cmd += ["-e", specialties]
    if start_date:
        cmd += ["--fecha-inicio", start_date]
    if end_date:
        cmd += ["--fecha-fin", end_date]
        
    # Copiamos el entorno y añadimos el ACTIVE_RUN_ID
    env = os.environ.copy()
    env["ACTIVE_RUN_ID"] = active_run_id
    
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True if sys.platform != 'win32' else False,
            env=env
        )
        return True
    except Exception as e:
        st.error(f"Error al arrancar el scraper en segundo plano: {e}")
        return False

def save_config_to_env(interval: float, run_once: bool, specialties: list, start_date: str, end_date: str):
    """
    Actualiza el archivo .env conservando comentarios y otras variables.
    """
    env_path = config.BASE_DIR / ".env"
    
    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    config_map = {
        "SCRAPING_INTERVAL_HOURS": f"{interval}\n",
        "RUN_ONCE": f"{str(run_once)}\n",
        "ESPECIALIDADES": f"{','.join(specialties)}\n",
        "FECHA_INICIO": f"{start_date}\n",
        "FECHA_FIN": f"{end_date}\n"
    }
    
    updated_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            parts = stripped.split("=", 1)
            key = parts[0].strip()
            if key in config_map:
                new_lines.append(f"{key}={config_map[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)
        
    for key, val in config_map.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")
            
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True
    except Exception as e:
        st.error(f"No se pudo guardar la configuración en .env: {e}")
        return False

# ==============================================================================
# PANEL LATERAL: SELECCIÓN DE EJECUCIÓN (VERSIONAMIENTO)
# ==============================================================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/e/e0/Escudo_nacional_del_Per%C3%BA.svg", width=65)
    st.markdown("### 🗂️ Historial de Versiones")
    
    # Obtener todas las versiones disponibles
    all_versions = get_all_runs()
    
    # Inicializar estado de sesión
    if "active_run_id" not in st.session_state:
        st.session_state["active_run_id"] = all_versions[0]
        
    if st.session_state["active_run_id"] not in all_versions:
        st.session_state["active_run_id"] = all_versions[0]
        
    # Dropdown de selector de versión activa
    selected_version = st.selectbox(
        "Ejecución activa a visualizar:",
        all_versions,
        index=all_versions.index(st.session_state["active_run_id"])
    )
    
    # Si cambia la versión seleccionada, actualizar la configuración dinámica
    if selected_version != st.session_state["active_run_id"]:
        st.session_state["active_run_id"] = selected_version
        st.rerun()
        
    # Cambiar rutas dinámicas de config para la sesión actual
    run_id = st.session_state["active_run_id"]
    os.environ["ACTIVE_RUN_ID"] = run_id
    config.ACTIVE_RUN_ID = run_id
    config.RUN_DIR = config.DATASET_DIR / "runs" / run_id
    config.METADATA_DIR = config.RUN_DIR / "metadata"
    config.CORPUS_DIR = config.RUN_DIR / "corpus_texto"
    config.TEMP_PAGES_DIR = config.METADATA_DIR / "temp_pages"
    config.PDF_CACHE_DIR = config.RUN_DIR / "cache_pdf"
    config.MAESTRO_RESOLUCIONES_CSV = config.METADATA_DIR / "maestro_resoluciones.csv"
    config.ARBOL_CONOCIMIENTO_CSV = config.METADATA_DIR / "arbol_conocimiento.csv"
    
    # Asegurar la existencia local de carpetas
    for d in [config.RUN_DIR, config.METADATA_DIR, config.CORPUS_DIR, config.TEMP_PAGES_DIR, config.PDF_CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        
    # Si la versión no tiene archivos CSV locales pero hay GCS configurado, descargarlos en caliente
    if config.GCS_BUCKET_NAME:
        if not config.MAESTRO_RESOLUCIONES_CSV.exists():
            download_from_gcs(
                config.GCS_BUCKET_NAME, 
                f"runs/{run_id}/metadata/maestro_resoluciones.csv", 
                config.MAESTRO_RESOLUCIONES_CSV
            )
        if not config.ARBOL_CONOCIMIENTO_CSV.exists():
            download_from_gcs(
                config.GCS_BUCKET_NAME, 
                f"runs/{run_id}/metadata/arbol_conocimiento.csv", 
                config.ARBOL_CONOCIMIENTO_CSV
            )

    st.markdown("---")
    st.markdown("### 🔍 Monitoreo de Scraper")
    
    # Monitorear estado de ejecución mediante el archivo PID
    running_pid = get_running_scraper_pid(config.SCRAPER_PID_FILE)
    
    if running_pid:
        st.markdown(
            f'<div class="status-badge status-active">🟢 EN EJECUCIÓN (PID: {running_pid})</div>', 
            unsafe_allow_html=True
        )
        if st.button("⏹️ Detener Extracción", use_container_width=True):
            if kill_scraper_process(config.SCRAPER_PID_FILE):
                st.toast("Señal de parada enviada al scraper.", icon="🛑")
                time.sleep(1.0)
                st.rerun()
    else:
        st.markdown(
            '<div class="status-badge status-stopped">🔴 DETENIDO / EN ESPERA</div>', 
            unsafe_allow_html=True
        )
        
    st.markdown("---")
    
    # Integración GCS
    st.markdown("#### ☁️ Integración de Cloud Storage")
    if config.GCS_BUCKET_NAME:
        st.success(f"Configurado en:\n`gs://{config.GCS_BUCKET_NAME}`")
        st.caption("Autenticación activa mediante ADC (WIF/Service Account).")
    else:
        st.info("Almacenamiento únicamente en disco local.")
        
    st.markdown("---")
    st.caption("Jurisprudencia Nacional Sistematizada v1.3")

# ==============================================================================
# CARGAR DATASETS PARA LA VERSIÓN SELECCIONADA
# ==============================================================================
df_maestro = load_maestro_data()
df_arbol = load_arbol_data()

# Encabezado principal
st.markdown('<div class="main-title">⚖️ Jurisprudencia Nacional</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitle"> ML-Ready Corpus & ETL Analytics — Versión Activa: <b>{run_id}</b></div>', unsafe_allow_html=True)

# ==============================================================================
# TARJETAS DE KPIs (Sondeo de archivos de la ejecución actual)
# ==============================================================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    pages_seeded = count_temp_pages()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">1. Enlaces Sembrados</div>
        <div class="metric-val">{pages_seeded}</div>
        <div style="font-size: 0.8rem; color:#94a3b8;">Archivos JSON de paginación</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    pdf_cached = count_cached_pdfs()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">2. PDFs en Caché</div>
        <div class="metric-val">{pdf_cached}</div>
        <div style="font-size: 0.8rem; color:#94a3b8;">Archivos listos para OCR</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    md_corpus = count_corpus_markdowns()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">3. Corpus Generado</div>
        <div class="metric-val">{md_corpus}</div>
        <div style="font-size: 0.8rem; color:#94a3b8;">Archivos Markdown extraídos</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    total_resoluciones = len(df_maestro) if not df_maestro.empty else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">4. Resoluciones Indexadas</div>
        <div class="metric-val">{total_resoluciones}</div>
        <div style="font-size: 0.8rem; color:#94a3b8;">Registros en maestro_resoluciones.csv</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gradient-divider"></div>', unsafe_allow_html=True)

# ==============================================================================
# TABS PRINCIPALES
# ==============================================================================
tab_stats, tab_explore, tab_control = st.tabs([
    "📈 Analítica & Volumetría", 
    "🔍 Explorador de Corpus", 
    "⚙️ Consola de Control"
])

# ------------------------------------------------------------------------------
# TAB 1: ANALÍTICA Y VOLUMETRÍA
# ------------------------------------------------------------------------------
with tab_stats:
    if df_maestro.empty:
        st.warning(f"⚠️ El maestro de resoluciones está vacío para la versión {run_id}. Usa la 'Consola de Control' para iniciar el scraper.")
    else:
        col_charts_1, col_charts_2 = st.columns(2)
        
        with col_charts_1:
            st.markdown("#### 🏛️ Resoluciones por Especialidad")
            fig_esp = px.bar(
                df_maestro['especialidad'].value_counts().reset_index(),
                x='especialidad',
                y='count',
                labels={'especialidad': 'Especialidad', 'count': 'Resoluciones'},
                color='count',
                color_continuous_scale='blues',
                template='plotly_dark'
            )
            fig_esp.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title=None)
            st.plotly_chart(fig_esp, use_container_width=True)
            
        with col_charts_2:
            st.markdown("#### 📅 Distribución Temporal")
            df_maestro['anio'] = df_maestro['fecha_resolucion'].apply(lambda x: str(x)[-4:] if len(str(x)) >= 4 else "Desconocido")
            fig_temporal = px.line(
                df_maestro['anio'].value_counts().sort_index().reset_index(),
                x='anio',
                y='count',
                labels={'anio': 'Año', 'count': 'Resoluciones'},
                markers=True,
                template='plotly_dark'
            )
            fig_temporal.update_traces(line_color='#38bdf8', marker_color='#818cf8', marker_size=8)
            fig_temporal.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title=None)
            st.plotly_chart(fig_temporal, use_container_width=True)
            
        st.markdown("---")
        
        col_charts_3, col_charts_4 = st.columns(2)
        
        with col_charts_3:
            st.markdown("#### 📑 Tipos de Documentos")
            fig_tipo = px.pie(
                df_maestro['tipo_resolucion'].value_counts().reset_index(),
                values='count',
                names='tipo_resolucion',
                hole=0.45,
                color_discrete_sequence=px.colors.sequential.Blues_r,
                template='plotly_dark'
            )
            fig_tipo.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_tipo, use_container_width=True)
            
        with col_charts_4:
            st.markdown("#### 🌿 Árbol de Jerarquía (Especialidad -> Delito/Pretensión)")
            if df_arbol.empty:
                st.info("No hay datos cargados para el árbol de conocimiento en esta ejecución.")
            else:
                fig_tree = px.treemap(
                    df_arbol,
                    path=['nivel_1_especialidad', 'nivel_2_delito_pretension'],
                    values='cantidad_documentos',
                    color='cantidad_documentos',
                    color_continuous_scale='Sunsetdark',
                    template='plotly_dark'
                )
                fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10))
                st.plotly_chart(fig_tree, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: EXPLORADOR DE CORPUS (Con descarga en caliente desde GCS)
# ------------------------------------------------------------------------------
with tab_explore:
    if df_maestro.empty:
        st.warning("El maestro de resoluciones está vacío.")
    else:
        st.markdown("#### 🔍 Filtros de Búsqueda del Corpus")
        col_fil_1, col_fil_2, col_fil_3 = st.columns([1, 1, 2])
        
        with col_fil_1:
            esp_lista = ["Todas"] + sorted(df_maestro['especialidad'].dropna().unique().tolist())
            filtro_esp = st.selectbox("Especialidad:", esp_lista, key="fil_esp_tab")
            
        with col_fil_2:
            if 'anio' not in df_maestro.columns:
                df_maestro['anio'] = df_maestro['fecha_resolucion'].apply(lambda x: str(x)[-4:] if len(str(x)) >= 4 else "Desconocido")
            anio_lista = ["Todos"] + sorted(df_maestro['anio'].dropna().unique().tolist())
            filtro_anio = st.selectbox("Año:", anio_lista, key="fil_anio_tab")
            
        with col_fil_3:
            busqueda = st.text_input("Búsqueda por Expediente, Delito o Sumilla:", "", placeholder="Ej: 001310-2022 o Homicidio...")
            
        # Filtrar datos
        df_filtered = df_maestro.copy()
        if filtro_esp != "Todas":
            df_filtered = df_filtered[df_filtered['especialidad'] == filtro_esp]
        if filtro_anio != "Todos":
            df_filtered = df_filtered[df_filtered['anio'] == filtro_anio]
        if busqueda:
            busqueda_clean = busqueda.lower()
            df_filtered = df_filtered[
                df_filtered['nro_expediente'].astype(str).str.lower().str.contains(busqueda_clean) |
                df_filtered['delito_pretension'].astype(str).str.lower().str.contains(busqueda_clean) |
                df_filtered['tipo_resolucion'].astype(str).str.lower().str.contains(busqueda_clean)
            ]
            
        st.markdown(f"**Coincidencias encontradas:** {len(df_filtered)}")
        
        # Split View Layout (Tabla a la izquierda, visor a la derecha)
        col_table, col_viewer = st.columns([5, 7])
        
        with col_table:
            st.markdown("##### 📄 Expedientes")
            display_cols = ['nro_expediente', 'especialidad', 'tipo_resolucion', 'fecha_resolucion', 'delito_pretension']
            selected_row = st.dataframe(
                df_filtered[display_cols],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="expediente_selector_table"
            )
            
        with col_viewer:
            st.markdown("##### 🔍 Detalle del Documento")
            
            selection = selected_row.get("selection")
            if selection and selection.get("rows"):
                row_idx = selection["rows"][0]
                selected_record = df_filtered.iloc[row_idx]
                
                # Ficha de metadatos
                st.markdown(f"""
                <div class="ficha-tecnica">
                    <span style="font-weight:700; color:#38bdf8; font-size:1.15rem;">EXP: {selected_record['nro_expediente']}</span><br>
                    <span style="color:#94a3b8; font-size:0.9rem;">UUID: {selected_record['uuid']}</span>
                    <hr style="border-color: rgba(255,255,255,0.06); margin: 0.8rem 0;">
                    <table style="width:100%; font-size:0.9rem; border-collapse:collapse; color:#cbd5e1;">
                        <tr><td style="font-weight:600; padding:4px 0; width:35%;">Especialidad:</td><td>{selected_record['especialidad']}</td></tr>
                        <tr><td style="font-weight:600; padding:4px 0;">Tipo Documento:</td><td>{selected_record['tipo_resolucion']}</td></tr>
                        <tr><td style="font-weight:600; padding:4px 0;">Fecha:</td><td>{selected_record['fecha_resolucion']}</td></tr>
                        <tr><td style="font-weight:600; padding:4px 0;">Órgano/Sala:</td><td>{selected_record['sala_suprema']}</td></tr>
                        <tr><td style="font-weight:600; padding:4px 0;">Delito/Pretensión:</td><td>{selected_record['delito_pretension']}</td></tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Ruta del Markdown físico
                md_rel_path = selected_record['ruta_markdown']
                md_full_path = config.DATASET_DIR / "runs" / run_id / md_rel_path
                
                # Descargar en caliente si no existe localmente pero hay bucket GCS
                if not md_full_path.exists() and config.GCS_BUCKET_NAME:
                    with st.spinner("Descargando documento desde GCS..."):
                        download_from_gcs(config.GCS_BUCKET_NAME, f"runs/{run_id}/{md_rel_path}", md_full_path)
                
                if md_full_path.exists():
                    try:
                        with open(md_full_path, "r", encoding="utf-8") as f:
                            md_content = f.read()
                            
                        clean_md = md_content
                        if md_content.startswith("---"):
                            parts = md_content.split("---", 2)
                            if len(parts) >= 3:
                                clean_md = parts[2].strip()
                                
                        st.download_button(
                            label="📥 Descargar Corpus (.md)",
                            data=md_content,
                            file_name=f"{selected_record['uuid']}.md",
                            mime="text/markdown",
                            use_container_width=True
                        )
                        
                        st.markdown('<div class="document-box">', unsafe_allow_html=True)
                        st.markdown(clean_md)
                        st.markdown('</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error al leer el archivo markdown: {e}")
                else:
                    st.warning(f"⚠️ El archivo markdown físico no está disponible en disco ni en GCS.")
            else:
                st.info("👈 Selecciona una resolución en la tabla para visualizar su contenido.")

# ------------------------------------------------------------------------------
# TAB 3: CONSOLA DE CONTROL DEL SCRAPER
# ------------------------------------------------------------------------------
with tab_control:
    col_control_left, col_control_right = st.columns([5, 7])
    
    with col_control_left:
        st.markdown("#### ⚙️ Control de Operaciones")
        
        if running_pid:
            st.info(f"El scraper se está ejecutando en segundo plano bajo el PID **{running_pid}**.")
            if st.button("🛑 Detener Ejecución del Scraper", type="primary", use_container_width=True):
                if kill_scraper_process(config.SCRAPER_PID_FILE):
                    st.success("Se envió la señal de detención al proceso.")
                    time.sleep(1.0)
                    st.rerun()
        else:
            st.markdown("Establece los parámetros y el rango de fechas para iniciar el scraper en una nueva versión.")
            
            sel_modo = st.radio(
                "Modo de ejecución:",
                ["Ejecución única (Una ronda completa con ID único)", "Ejecución programada (Bucle continuo)"]
            )
            
            sel_intervalo = st.slider(
                "Intervalo entre rondas (Horas) - Solo para modo programado:",
                min_value=1.0,
                max_value=72.0,
                value=12.0,
                step=0.5
            )
            
            # Filtro por Rango de Fechas (DatePicker)
            st.markdown("##### 📅 Rango de Fechas Exacto (Fecha Resolución)")
            col_date_start, col_date_end = st.columns(2)
            
            # Recuperar fechas por defecto del .env/entorno si existen
            env_start_date_str = os.getenv("FECHA_INICIO", "")
            env_end_date_str = os.getenv("FECHA_FIN", "")
            
            default_start_date = date(2025, 1, 1)
            default_end_date = date.today()
            
            if env_start_date_str:
                try:
                    default_start_date = datetime.strptime(env_start_date_str, "%d/%m/%Y").date()
                except:
                    pass
            if env_end_date_str:
                try:
                    default_end_date = datetime.strptime(env_end_date_str, "%d/%m/%Y").date()
                except:
                    pass
            
            with col_date_start:
                sel_start_date = st.date_input("Fecha Inicio:", default_start_date)
            with col_date_end:
                sel_end_date = st.date_input("Fecha Fin:", default_end_date)
                
            # Especialidades multiselect
            opciones_especialidades = list(config.ESPECIALIDADES.keys())
            
            # Especialidades preseleccionadas del env
            env_esp_str = os.getenv("ESPECIALIDADES", "civil,penal")
            default_esp = [e.strip() for e in env_esp_str.split(",") if e.strip() in opciones_especialidades]
            if not default_esp:
                default_esp = ["civil", "penal"]
                
            sel_especialidades = st.multiselect(
                "Especialidades a escanear (Vacío = Todas):",
                opciones_especialidades,
                default=default_esp
            )
            
            st.markdown("---")
            col_btn_save, col_btn_run = st.columns(2)
            
            # Convertir fechas a string DD/MM/YYYY
            start_date_str = sel_start_date.strftime("%d/%m/%Y")
            end_date_str = sel_end_date.strftime("%d/%m/%Y")
            
            with col_btn_save:
                if st.button("💾 Guardar Config en .env", use_container_width=True):
                    is_once = "Una ronda" in sel_modo
                    if save_config_to_env(sel_intervalo, is_once, sel_especialidades, start_date_str, end_date_str):
                        st.toast("Configuración guardada en .env.", icon="💾")
                        time.sleep(0.5)
                        st.rerun()
            
            with col_btn_run:
                if st.button("🚀 Iniciar Extracción", type="primary", use_container_width=True):
                    is_once = "Una ronda" in sel_modo
                    # Guardamos la configuración primero
                    save_config_to_env(sel_intervalo, is_once, sel_especialidades, start_date_str, end_date_str)
                    
                    # Generar una carpeta/ID único de ejecución basado en timestamp
                    new_run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # Crear carpetas locales de inmediato
                    new_run_dir = config.DATASET_DIR / "runs" / new_run_id
                    for d in [new_run_dir, new_run_dir / "metadata", new_run_dir / "metadata" / "temp_pages", new_run_dir / "cache_pdf", new_run_dir / "corpus_texto"]:
                        d.mkdir(parents=True, exist_ok=True)
                        
                    # Configurar variables del entorno para pasarlas al orquestador
                    esp_args = ",".join(sel_especialidades)
                    modo_str = "once" if is_once else "loop"
                    
                    # Guardar ACTIVE_RUN_ID en session state para visualizarla
                    st.session_state["active_run_id"] = new_run_id
                    
                    if start_scraper_subprocess(modo_str, sel_intervalo, esp_args, start_date_str, end_date_str, new_run_id):
                        st.success(f"Extracción iniciada en versión: {new_run_id}")
                        time.sleep(1.0)
                        st.rerun()
                        
    with col_control_right:
        st.markdown("#### 📋 Bitácora del Pipeline (orchestrator.log)")
        
        # Botón para limpiar logs
        col_logs_1, col_logs_2 = st.columns([3, 1])
        with col_logs_2:
            if st.button("🧹 Limpiar Log", use_container_width=True):
                log_file = config.DATASET_DIR / "orchestrator.log"
                if log_file.exists():
                    try:
                        log_file.unlink()
                        st.success("Logs de consola limpiados.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        # Contenedor dinámico de logs
        log_file = config.DATASET_DIR / "orchestrator.log"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                    log_lines = f.readlines()
                
                last_lines = log_lines[-35:] if len(log_lines) > 35 else log_lines
                log_text = "".join(last_lines)
                st.markdown(f'<pre class="log-console">{log_text}</pre>', unsafe_allow_html=True)
            except Exception as e:
                st.error(f"No se pudo leer el archivo de log: {e}")
        else:
            st.markdown('<pre class="log-console">Esperando primera ejecución... No hay logs disponibles en disco.</pre>', unsafe_allow_html=True)
            
        # Refrescar automático si el scraper está en ejecución
        if running_pid:
            time.sleep(2.0)
            st.rerun()
