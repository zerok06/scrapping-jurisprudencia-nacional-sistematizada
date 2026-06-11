import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path
from datetime import datetime

# Importar configuración y utilidades
import config
from utils import list_gcs_runs

# Cargar variables SMTP del entorno/dotenv
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
except:
    SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
EMAIL_RECIPIENTS_STR = os.getenv("EMAIL_RECIPIENTS", "jose.geeksjose@gmail.com,honorio.apz@gmail.com")
RECIPIENTS = [r.strip() for r in EMAIL_RECIPIENTS_STR.split(",") if r.strip()]

def get_runs_stats():
    """
    Recopila estadísticas de las ejecuciones locales para incluirlas en el reporte.
    """
    stats = []
    runs_dir = config.DATASET_DIR / "runs"
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir(), key=lambda x: x.name, reverse=True):
            if d.is_dir() and d.name.startswith("run_"):
                # Contar resoluciones indexadas locales
                maestro_csv = d / "metadata" / "maestro_resoluciones.csv"
                qty = 0
                if maestro_csv.exists():
                    try:
                        import pandas as pd
                        df = pd.read_csv(maestro_csv)
                        qty = len(df)
                    except:
                        pass
                
                # Contar markdowns
                corpus_dir = d / "corpus_texto"
                md_qty = 0
                if corpus_dir.exists():
                    md_qty = len(list(corpus_dir.glob("**/*.md")))
                    
                stats.append({
                    "run_id": d.name,
                    "records": qty,
                    "markdowns": md_qty
                })
    return stats

def compile_report_body() -> str:
    """
    Compila el texto del correo con el resumen general.
    """
    active_run = config.ACTIVE_RUN_ID
    run_dir = config.RUN_DIR
    
    # Contar archivos físicos locales de la ejecución activa
    temp_pages_dir = config.TEMP_PAGES_DIR
    pdf_cache_dir = config.PDF_CACHE_DIR
    corpus_dir = config.CORPUS_DIR
    
    pages_seeded = len(list(temp_pages_dir.glob("tmp_*.json"))) if temp_pages_dir.exists() else 0
    pdf_cached = len(list(pdf_cache_dir.glob("*.pdf"))) if pdf_cache_dir.exists() else 0
    md_corpus = len(list(corpus_dir.glob("**/*.md"))) if corpus_dir.exists() else 0
    
    total_resoluciones = 0
    if config.MAESTRO_RESOLUCIONES_CSV.exists():
        try:
            import pandas as pd
            df = pd.read_csv(config.MAESTRO_RESOLUCIONES_CSV)
            total_resoluciones = len(df)
        except:
            pass

    # Estado del GCS
    gcs_status = f"Configurado (gs://{config.GCS_BUCKET_NAME})" if config.GCS_BUCKET_NAME else "No configurado (Solo almacenamiento local)"
    
    # Obtener historial de ejecuciones locales
    history = get_runs_stats()
    history_text = ""
    for h in history[:5]: # Mostrar las últimas 5
        history_text += f"- {h['run_id']}: {h['records']} resoluciones indexadas, {h['markdowns']} markdowns generados.\n"
    if not history_text:
        history_text = "Sin ejecuciones históricas registradas en disco.\n"

    body = f"""REPORTE DIARIO DE ESTADO — JURISPRUDENCIA NACIONAL SISTEMATIZADA
Fecha del Reporte: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (PET/UTC-5)

========================================================================
1. RESUMEN DE LA EJECUCIÓN ACTIVA / ÚLTIMA
========================================================================
- ID de Ejecución: {active_run}
- Enlaces Sembrados (JSON Paginados): {pages_seeded}
- PDFs en Caché (Pendientes de OCR): {pdf_cached}
- Corpus Markdown Generado (Listos para LLMs): {md_corpus}
- Resoluciones Consolidadas en Maestro CSV: {total_resoluciones}

========================================================================
2. CONFIGURACIÓN Y FILTROS APLICADOS
========================================================================
- Rango de Fechas: {os.getenv('FECHA_INICIO', 'No especificado')} a {os.getenv('FECHA_FIN', 'No especificado')}
- Especialidades: {os.getenv('ESPECIALIDADES', 'Todas')}
- Intervalo automático: {os.getenv('SCRAPING_INTERVAL_HOURS', '12.0')} horas
- Almacenamiento en Google Cloud Storage: {gcs_status}

========================================================================
3. HISTORIAL DE EJECUCIONES RECIENTES EN DISCO
========================================================================
{history_text}
========================================================================

Este es un correo automático generado por el orquestador de Jurisprudencia Nacional.
"""
    return body

def send_email_report():
    """
    Compila el reporte y lo envía a los destinatarios mediante SMTP.
    """
    subject = f"Reporte de Scraping Jurisprudencia — {datetime.now().strftime('%d/%m/%Y')}"
    body = compile_report_body()
    
    print("\n=== CONTENIDO DEL REPORTE POR CORREO ===")
    print(body)
    print("========================================\n")
    
    if not RECIPIENTS:
        print("[REPORTER WARN] No se especificaron destinatarios en EMAIL_RECIPIENTS.")
        return False
        
    if not SMTP_USER or not SMTP_PASSWORD:
        print("[REPORTER WARN] SMTP_USER o SMTP_PASSWORD vacíos. El reporte NO se envió por correo (se imprimió arriba para depuración).")
        return True
        
    try:
        # Configurar el mensaje
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(RECIPIENTS)
        
        # Conexión SMTP
        print(f"[REPORTER] Conectando a {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.ehlo()
        if SMTP_PORT == 587:
            server.starttls() # Asegurar TLS si es puerto 587
            server.ehlo()
            
        print(f"[REPORTER] Iniciando sesión como {SMTP_USER}...")
        server.login(SMTP_USER, SMTP_PASSWORD)
        
        print(f"[REPORTER] Enviando correo a: {RECIPIENTS}...")
        server.sendmail(SMTP_USER, RECIPIENTS, msg.as_string())
        server.quit()
        
        print("[REPORTER SUCCESS] Reporte de correo enviado exitosamente.")
        return True
    except Exception as e:
        print(f"[REPORTER ERROR] Fallo al enviar el reporte por correo: {e}")
        return False

if __name__ == "__main__":
    send_email_report()
