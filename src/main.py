import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# Configuración y utilidades
from config import SCRAPER_PID_FILE
from utils import write_scraper_pid

# Reconfigurar codificación de terminal para evitar UnicodeEncodeError en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
DATASET_DIR = BASE_DIR / "jurisprudencia_dataset"
LOG_FILE = DATASET_DIR / "orchestrator.log"

def safe_print(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or 'utf-8'
            encoded_text = text.encode(encoding, errors='replace').decode(encoding)
            print(encoded_text)
        except Exception:
            # Fallback definitivo
            print(text.encode('ascii', errors='ignore').decode('ascii'))

def parse_arguments():
    # Cargar defaults desde el env
    default_interval = float(os.getenv("SCRAPING_INTERVAL_HOURS", "12.0"))
    default_run_once = os.getenv("RUN_ONCE", "False").lower() == "true"
    default_especialidades = os.getenv("ESPECIALIDADES", "")
    default_anios = os.getenv("ANIOS", "")

    parser = argparse.ArgumentParser(description="Orquestador del Scraper de Jurisprudencia Nacional")
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=default_interval,
        help=f"Intervalo en horas entre rondas de ejecución (por defecto: {default_interval})"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=default_run_once,
        help=f"Ejecutar la secuencia una sola vez y salir (por defecto: {default_run_once})"
    )
    parser.add_argument(
        "-e", "--especialidades",
        type=str,
        default=default_especialidades,
        help="Lista de especialidades separadas por comas"
    )
    parser.add_argument(
        "-y", "--anios",
        type=str,
        default=default_anios,
        help="Lista de años separados por comas"
    )
    return parser.parse_args()

def log_message(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    safe_print(formatted_msg)
    
    # Crear carpeta si no existe y escribir en log
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted_msg + "\n")

def run_module(script_name: str, args_list: list) -> bool:
    script_path = SRC_DIR / script_name
    cmd = [sys.executable, str(script_path)] + args_list
    
    log_message(f"Iniciando ejecución de módulo: {script_name}...")
    log_message(f"Comando: {' '.join(cmd)}")
    
    try:
        # Ejecutar capturando salida en tiempo real en consola e internalizando errores
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )
        
        # Leer la salida línea por línea y volcarla al log de orquestación
        if process.stdout:
            for line in process.stdout:
                clean_line = line.rstrip()
                # Logear salida para diagnóstico
                if clean_line:
                    # Escribir solo al archivo de log para no saturar st.stdout
                    with open(LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"[{script_name}] {clean_line}\n")
                    safe_print(f"[{script_name}] {clean_line}")
                    
        return_code = process.wait()
        if return_code == 0:
            log_message(f"Módulo {script_name} completado con éxito.")
            return True
        else:
            log_message(f"[ERROR] Módulo {script_name} falló con código de salida {return_code}.")
            return False
            
    except Exception as e:
        log_message(f"[ERROR] Excepción al iniciar el módulo {script_name}: {e}")
        return False

def execute_pipeline(args):
    log_message("=== INICIANDO RONDA DE EJECUCIÓN DEL PIPELINE ===")
    
    # Módulo A: Seeder
    seeder_args = ["--headless"]
    if args.especialidades:
        seeder_args += ["-e", args.especialidades]
    if args.anios:
        seeder_args += ["-y", args.anios]
        
    seeder_ok = run_module("seeder.py", seeder_args)
    if not seeder_ok:
        log_message("[WARN] Módulo Seeder falló. Continuando con descargas de registros previos.")

    # Módulo B: Downloader
    downloader_ok = run_module("downloader.py", [])
    if not downloader_ok:
        log_message("[WARN] Módulo Downloader reportó errores durante las descargas.")

    # Módulo C: NLP Pipeline
    nlp_ok = run_module("nlp_pipeline.py", [])
    if not nlp_ok:
        log_message("[WARN] Módulo NLP reportó errores al procesar PDFs.")

    # Módulo Consolidator
    consolidator_ok = run_module("consolidator.py", [])
    if not consolidator_ok:
        log_message("[ERROR] Módulo Consolidator falló. El dataset maestro puede no estar actualizado.")
        
    log_message("=== FINALIZADA RONDA DE EJECUCIÓN DEL PIPELINE ===\n")

def main():
    args = parse_arguments()
    
    # Limpiar archivo de log viejo al arrancar
    if LOG_FILE.exists():
        try:
            LOG_FILE.unlink()
        except:
            pass
            
    # Registrar PID
    write_scraper_pid(SCRAPER_PID_FILE, os.getpid())
    
    try:
        log_message(f"Orquestador iniciado (PID: {os.getpid()}). Ejecutar una vez: {args.once}. Intervalo: {args.interval} horas.")
        
        if args.once:
            execute_pipeline(args)
            log_message("Ejecución única completada. Saliendo.")
            return
            
        # Bucle continuo
        interval_seconds = args.interval * 3600
        while True:
            try:
                execute_pipeline(args)
            except KeyboardInterrupt:
                log_message("Orquestador detenido por el usuario.")
                break
            except Exception as e:
                log_message(f"[CRÍTICO] Excepción no controlada en el bucle principal: {e}")
                
            log_message(f"Esperando {args.interval} horas para la siguiente ronda...")
            # Espera granular para poder responder a detenciones rápido
            sleep_step = 10
            total_slept = 0
            while total_slept < interval_seconds:
                time.sleep(sleep_step)
                total_slept += sleep_step
    finally:
        # Limpiar archivo de PID al salir
        if SCRAPER_PID_FILE.exists():
            try:
                SCRAPER_PID_FILE.unlink()
            except:
                pass
        log_message("Orquestador finalizado. PID liberado.")

if __name__ == "__main__":
    main()
