import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Configuración de página
st.set_page_config(
    page_title="Dashboard - Jurisprudencia Nacional",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS personalizado para un look Premium (Dark Theme con Glassmorphism)
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
<style>
    /* Aplicar fuente general */
    html, body, [class*="css"], .stText, p, span, h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif !important;
    }
    
    /* Fondo principal y diseño oscuro */
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    
    /* Panel lateral */
    section[data-testid="stSidebar"] {
        background-color: #161b22 !important;
        border-right: 1px solid #30363d;
    }
    
    /* Encabezados y títulos con gradiente */
    .main-title {
        background: linear-gradient(135deg, #00f2fe, #4facfe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin-bottom: 0.2rem;
    }
    
    .subtitle {
        color: #8b949e;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    /* Tarjetas de métricas personalizadas (Glassmorphism) */
    .metric-card {
        background: rgba(22, 27, 34, 0.7);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(10px);
        transition: transform 0.2s ease, border-color 0.2s ease;
        text-align: center;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: #58a6ff;
    }
    
    .metric-val {
        font-size: 2.2rem;
        font-weight: 800;
        color: #58a6ff;
        margin: 0.5rem 0;
    }
    
    .metric-label {
        font-size: 0.95rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Divisor de gradiente */
    .gradient-divider {
        height: 2px;
        background: linear-gradient(90deg, #4facfe, #00f2fe, transparent);
        margin: 2rem 0;
    }
    
    /* Contenedor de visualización de documentos */
    .document-box {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 2rem;
        max-height: 600px;
        overflow-y: auto;
        color: #e6edf3;
    }
    
    /* Estilos de botones */
    div.stButton > button {
        background: linear-gradient(135deg, #00c6ff, #0072ff);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.6rem 1.2rem;
        transition: all 0.3s ease;
    }
    
    div.stButton > button:hover {
        transform: scale(1.03);
        box-shadow: 0 5px 15px rgba(0, 198, 255, 0.4);
        color: white;
    }
    
    /* Consola de logs */
    .log-console {
        background-color: #000000;
        color: #00ff66;
        font-family: 'Courier New', monospace !important;
        padding: 1rem;
        border-radius: 6px;
        border: 1px solid #30363d;
        font-size: 0.85rem;
        max-height: 350px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "jurisprudencia_dataset"
METADATA_DIR = DATASET_DIR / "metadata"
CORPUS_DIR = DATASET_DIR / "corpus_texto"
PDF_CACHE_DIR = DATASET_DIR / "cache_pdf"
TEMP_PAGES_DIR = METADATA_DIR / "temp_pages"

MAESTRO_RESOLUCIONES_CSV = METADATA_DIR / "maestro_resoluciones.csv"
ARBOL_CONOCIMIENTO_CSV = METADATA_DIR / "arbol_conocimiento.csv"
ORCHESTRATOR_LOG = DATASET_DIR / "orchestrator.log"

# Cargar archivos de datos de forma segura
@st.cache_data(ttl=10)
def load_maestro_data():
    if not MAESTRO_RESOLUCIONES_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(MAESTRO_RESOLUCIONES_CSV)
        # Asegurar tipos
        df['uuid'] = df['uuid'].astype(str)
        return df
    except Exception as e:
        st.error(f"Error al leer maestro_resoluciones.csv: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=10)
def load_arbol_data():
    if not ARBOL_CONOCIMIENTO_CSV.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(ARBOL_CONOCIMIENTO_CSV)
    except Exception as e:
        st.error(f"Error al leer arbol_conocimiento.csv: {e}")
        return pd.DataFrame()

# Funciones helper para contar archivos físicos
def count_temp_pages():
    if not TEMP_PAGES_DIR.exists():
        return 0
    return len(list(TEMP_PAGES_DIR.glob("tmp_*.json")))

def count_cached_pdfs():
    if not PDF_CACHE_DIR.exists():
        return 0
    return len(list(PDF_CACHE_DIR.glob("*.pdf")))

def count_corpus_markdowns():
    if not CORPUS_DIR.exists():
        return 0
    return len(list(CORPUS_DIR.glob("**/*.md")))

# Estructurar app
def run_scraper_subprocess(args_str=""):
    script_path = BASE_DIR / "src" / "main.py"
    cmd = [sys.executable, str(script_path), "--once"]
    if args_str:
        cmd += args_str.split()
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

# ==============================================================================
# INTERFAZ PRINCIPAL
# ==============================================================================

# Encabezado
st.markdown('<div class="main-title">⚖️ Jurisprudencia Nacional Sistematizada</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">ML-ready Corpus & Pipeline Analytics - Poder Judicial del Perú</div>', unsafe_allow_html=True)

# Cargar datos
df_maestro = load_maestro_data()
df_arbol = load_arbol_data()

# ==============================================================================
# BARRA LATERAL (CONTROLES)
# ==============================================================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/e/e0/Escudo_nacional_del_Per%C3%BA.svg", width=80)
    st.markdown("### ⚙️ Centro de Control")
    st.markdown("---")
    
    # Visualizar estado actual del scraper
    # Verificar si el orquestador o scripts individuales están corriendo
    # En sistemas operativos esto varía, buscamos en session state
    if "scraping_running" not in st.session_state:
        st.session_state["scraping_running"] = False
        
    status_color = "🔴 DETENIDO" if not st.session_state["scraping_running"] else "🟢 EN EJECUCIÓN"
    st.markdown(f"**Estado del Scraper:** {status_color}")
    
    st.markdown("---")
    st.markdown("#### Ejecutar Tarea Manual")
    
    esp_opciones = {
        "Todas": "",
        "Civil": "civil",
        "Penal": "penal",
        "Constitucional": "constitucional",
        "Laboral": "laboral",
        "Familia (Civil)": "familia_civil"
    }
    sel_esp = st.selectbox("Especialidad:", list(esp_opciones.keys()))
    
    anios_opciones = ["Todos", "2026", "2025", "2024", "2023", "2022", "2021"]
    sel_anio = st.selectbox("Año de interés:", anios_opciones)
    
    run_btn = st.button("🚀 Iniciar Extracción")
    
    if run_btn:
        if st.session_state["scraping_running"]:
            st.warning("Ya hay una ronda de ejecución activa.")
        else:
            args_list = []
            if esp_opciones[sel_esp]:
                args_list.append(f"-e {esp_opciones[sel_esp]}")
            if sel_anio != "Todos":
                args_list.append(f"-y {sel_anio}")
                
            args_str = " ".join(args_list)
            
            st.session_state["process"] = run_scraper_subprocess(args_str)
            st.session_state["scraping_running"] = True
            st.rerun()

    # Botón para detener si está corriendo
    if st.session_state["scraping_running"]:
        stop_btn = st.button("⏹️ Forzar Parada")
        if stop_btn:
            if "process" in st.session_state:
                st.session_state["process"].terminate()
            st.session_state["scraping_running"] = False
            st.success("Scraper detenido de forma segura.")
            st.rerun()

    st.markdown("---")
    st.markdown("#### Configuración de Pipeline")
    st.info("Para VPS de bajos recursos, los archivos PDF se eliminan automáticamente de la caché física una vez convertidos a Markdown.")

# ==============================================================================
# TARJETAS DE MÉTRICAS (KPIs)
# ==============================================================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    pages_seeded = count_temp_pages()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Páginas Sembradas</div>
        <div class="metric-val">{pages_seeded}</div>
        <div style="font-size: 0.8rem; color:#8b949e;">Índices temporales JSON</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    pdf_cached = count_cached_pdfs()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">PDFs en Caché</div>
        <div class="metric-val">{pdf_cached}</div>
        <div style="font-size: 0.8rem; color:#8b949e;">Pendientes de extracción NLP</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    md_corpus = count_corpus_markdowns()
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Corpus Markdown</div>
        <div class="metric-val">{md_corpus}</div>
        <div style="font-size: 0.8rem; color:#8b949e;">Archivos listos para LLMs</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    total_resoluciones = len(df_maestro) if not df_maestro.empty else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Resoluciones Indexadas</div>
        <div class="metric-val">{total_resoluciones}</div>
        <div style="font-size: 0.8rem; color:#8b949e;">Registros en Maestro CSV</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gradient-divider"></div>', unsafe_allow_html=True)

# ==============================================================================
# SECCIÓN DE LOGS EN VIVO (Si está corriendo)
# ==============================================================================
if st.session_state["scraping_running"]:
    st.markdown("### 📋 Bitácora de Ejecución en Tiempo Real")
    log_area = st.empty()
    
    # Monitorear proceso
    p = st.session_state.get("process")
    if p:
        # Check if process is done
        ret = p.poll()
        if ret is not None:
            st.session_state["scraping_running"] = False
            st.success("Extracción completada!")
            st.rerun()
            
    # Leer el log file para mostrar las últimas líneas
    if ORCHESTRATOR_LOG.exists():
        with open(ORCHESTRATOR_LOG, "r", encoding="utf-8-sig", errors="ignore") as f:
            log_lines = f.readlines()
        
        last_lines = log_lines[-15:] if len(log_lines) > 15 else log_lines
        log_text = "".join(last_lines)
        log_area.markdown(f'<pre class="log-console">{log_text}</pre>', unsafe_allow_html=True)
    else:
        log_area.markdown('<pre class="log-console">Iniciando pipeline... esperando logs...</pre>', unsafe_allow_html=True)
        
    time.sleep(1)
    st.rerun()

# ==============================================================================
# TABS PRINCIPALES DE VISUALIZACIÓN
# ==============================================================================
tab_stats, tab_explore, tab_tree = st.tabs([
    "📈 Estadísticas del Dataset", 
    "🔍 Explorador de Corpus", 
    "🌿 Árbol de Conocimiento"
])

# ------------------------------------------------------------------------------
# TAB 1: ESTADÍSTICAS DEL DATASET
# ------------------------------------------------------------------------------
with tab_stats:
    if df_maestro.empty:
        st.warning("El maestro de resoluciones está vacío. Por favor, corre el scraper en la barra lateral para empezar a poblar los datos.")
    else:
        col_charts_1, col_charts_2 = st.columns(2)
        
        with col_charts_1:
            st.markdown("#### Especialidades más Frecuentes")
            fig_esp = px.bar(
                df_maestro['especialidad'].value_counts().reset_index(),
                x='especialidad',
                y='count',
                labels={'especialidad': 'Especialidad', 'count': 'Cant. Resoluciones'},
                color='count',
                color_continuous_scale='tealgrn',
                template='plotly_dark'
            )
            fig_esp.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_esp, use_container_width=True)
            
        with col_charts_2:
            st.markdown("#### Distribución Temporal (Año de Resolución)")
            # Extraer año de la fecha de resolución
            df_maestro['anio'] = df_maestro['fecha_resolucion'].apply(lambda x: str(x)[-4:] if len(str(x)) >= 4 else "Desconocido")
            fig_temporal = px.line(
                df_maestro['anio'].value_counts().sort_index().reset_index(),
                x='anio',
                y='count',
                labels={'anio': 'Año de Resolución', 'count': 'Cant. Resoluciones'},
                markers=True,
                template='plotly_dark'
            )
            fig_temporal.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_temporal, use_container_width=True)
            
        st.markdown("---")
        col_charts_3, col_charts_4 = st.columns(2)
        
        with col_charts_3:
            st.markdown("#### Tipos de Resolución")
            fig_tipo = px.pie(
                df_maestro['tipo_resolucion'].value_counts().reset_index(),
                values='count',
                names='tipo_resolucion',
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Plasma,
                template='plotly_dark'
            )
            fig_tipo.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_tipo, use_container_width=True)
            
        with col_charts_4:
            st.markdown("#### Órganos Jurisdiccionales / Salas")
            fig_sala = px.bar(
                df_maestro['sala_suprema'].value_counts().head(8).reset_index(),
                y='sala_suprema',
                x='count',
                orientation='h',
                labels={'sala_suprema': 'Sala Suprema', 'count': 'Resoluciones'},
                color='count',
                color_continuous_scale='Viridis',
                template='plotly_dark'
            )
            fig_sala.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_sala, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: EXPLORADOR DE CORPUS
# ------------------------------------------------------------------------------
with tab_explore:
    if df_maestro.empty:
        st.warning("El maestro de resoluciones está vacío.")
    else:
        # Filtros interactivos
        col_filtro_1, col_filtro_2, col_filtro_3 = st.columns([1, 1, 2])
        
        with col_filtro_1:
            esp_lista = ["Todas"] + sorted(df_maestro['especialidad'].dropna().unique().tolist())
            filtro_esp = st.selectbox("Filtrar Especialidad:", esp_lista, key="fil_esp")
            
        with col_filtro_2:
            df_maestro['anio'] = df_maestro['fecha_resolucion'].apply(lambda x: str(x)[-4:] if len(str(x)) >= 4 else "Desconocido")
            anio_lista = ["Todos"] + sorted(df_maestro['anio'].dropna().unique().tolist())
            filtro_anio = st.selectbox("Filtrar Año:", anio_lista, key="fil_anio")
            
        with col_filtro_3:
            busqueda = st.text_input("🔍 Buscar por Número de Expediente o Delito:", "", placeholder="Ej: 001310-2022 o Homicidio")

        # Aplicar filtros
        df_filtered = df_maestro.copy()
        if filtro_esp != "Todas":
            df_filtered = df_filtered[df_filtered['especialidad'] == filtro_esp]
        if filtro_anio != "Todos":
            df_filtered = df_filtered[df_filtered['anio'] == filtro_anio]
        if busqueda:
            busqueda_clean = busqueda.lower()
            df_filtered = df_filtered[
                df_filtered['nro_expediente'].astype(str).str.lower().str.contains(busqueda_clean) |
                df_filtered['delito_pretension'].astype(str).str.lower().str.contains(busqueda_clean)
            ]

        st.markdown(f"**Documentos coincidentes:** {len(df_filtered)}")
        
        # Tabla interactiva
        # Seleccionar columnas relevantes para mostrar
        display_cols = ['uuid', 'nro_expediente', 'especialidad', 'tipo_resolucion', 'fecha_resolucion', 'delito_pretension']
        
        # Agregamos selector de filas
        selected_row_index = st.dataframe(
            df_filtered[display_cols],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )
        
        # Ver si hay selección
        selection = selected_row_index.get("selection")
        if selection and selection.get("rows"):
            row_idx = selection["rows"][0]
            selected_record = df_filtered.iloc[row_idx]
            
            st.markdown("---")
            st.markdown(f"### 📄 Visualizador de Documento: {selected_record['nro_expediente']}")
            
            col_meta_1, col_meta_2 = st.columns([1, 2])
            
            with col_meta_1:
                st.markdown("#### Metadatos")
                meta_table = pd.DataFrame([
                    {"Campo": "UUID", "Valor": selected_record['uuid']},
                    {"Campo": "Expediente", "Valor": selected_record['nro_expediente']},
                    {"Campo": "Especialidad", "Valor": selected_record['especialidad']},
                    {"Campo": "Tipo de Resolución", "Valor": selected_record['tipo_resolucion']},
                    {"Campo": "Fecha", "Valor": selected_record['fecha_resolucion']},
                    {"Campo": "Órgano Jurisdiccional", "Valor": selected_record['sala_suprema']},
                    {"Campo": "Delito/Pretensión", "Valor": selected_record['delito_pretension']},
                ])
                st.table(meta_table.set_index("Campo"))
                
            with col_meta_2:
                st.markdown("#### Contenido del Archivo Markdown")
                
                # Intentar leer el Markdown físico en disco
                md_relative_path = selected_record['ruta_markdown']
                md_full_path = DATASET_DIR / md_relative_path
                
                if md_full_path.exists():
                    try:
                        with open(md_full_path, "r", encoding="utf-8") as f:
                            md_content = f.read()
                            
                        # Extraer solo el texto (ocultar el yaml front matter para una lectura más limpia)
                        # El front matter está delimitado por ---
                        clean_content = md_content
                        if md_content.startswith("---"):
                            parts = md_content.split("---", 2)
                            if len(parts) >= 3:
                                clean_content = parts[2].strip()
                                
                        st.markdown(f'<div class="document-box">', unsafe_allow_html=True)
                        st.markdown(clean_content)
                        st.markdown('</div>', unsafe_allow_html=True)
                    except Exception as ex:
                        st.error(f"No se pudo leer el archivo Markdown físico: {ex}")
                else:
                    st.warning(f"El archivo Markdown físico no se encuentra en la ruta esperada: `{md_relative_path}`. Esto puede deberse a que el descargador o el pipeline de NLP aún no se han ejecutado para este UUID.")

# ------------------------------------------------------------------------------
# TAB 3: ÁRBOL DE CONOCIMIENTO (VOLUMETRÍA CONCEPTUAL)
# ------------------------------------------------------------------------------
with tab_tree:
    if df_arbol.empty:
        st.warning("El árbol de conocimiento está vacío. Ejecute el consolidador para generarlo.")
    else:
        st.markdown("### 🌿 Volumetría Conceptual de Resoluciones")
        st.markdown("El árbol agrupa jerárquicamente los expedientes por Especialidad (Nivel 1) y Delito/Pretensión (Nivel 2) para scannability rápida del dataset.")
        
        # Treemap
        fig_tree = px.treemap(
            df_arbol,
            path=['nivel_1_especialidad', 'nivel_2_delito_pretension'],
            values='cantidad_documentos',
            color='cantidad_documentos',
            color_continuous_scale='Sunsetdark',
            title='Distribución Jerárquica del Corpus de Jurisprudencia',
            template='plotly_dark'
        )
        st.plotly_chart(fig_tree, use_container_width=True)
        
        st.markdown("---")
        st.markdown("#### Detalle de Categorías")
        
        # Mostrar tabla ordenada
        st.dataframe(
            df_arbol[['nivel_1_especialidad', 'nivel_2_delito_pretension', 'cantidad_documentos', 'categoria_id']],
            use_container_width=True,
            hide_index=True
        )
