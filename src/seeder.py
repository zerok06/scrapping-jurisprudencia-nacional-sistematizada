import argparse
import asyncio
import math
import re
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# Importar configuración y utilidades
from config import (
    PORTAL_URL,
    ESPECIALIDADES,
    ANOS_INTERES,
    NIVEL_CORTE_POR_DEFECTO,
    TEMP_PAGES_DIR
)
from utils import save_json, clean_string, clean_yaml_field

def parse_arguments():
    parser = argparse.ArgumentParser(description="Sembrador Granular de Jurisprudencia del Poder Judicial del Perú")
    parser.add_argument(
        "-e", "--especialidades",
        type=str,
        default=",".join(ESPECIALIDADES.keys()),
        help=f"Especialidades a raspar separadas por comas. Opciones: {list(ESPECIALIDADES.keys())}"
    )
    parser.add_argument(
        "-y", "--anios",
        type=str,
        default=",".join(ANOS_INTERES),
        help=f"Años a raspar separados por comas. Ejemplo: 2024,2025"
    )
    parser.add_argument(
        "-c", "--corte",
        type=str,
        default=NIVEL_CORTE_POR_DEFECTO,
        help="Nivel/Corte: 1 para Corte Suprema (por defecto), 2 para Corte Superior"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Ejecutar el navegador en modo oculto (headless)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forzar el raspado de páginas existentes (sobrescribir JSON temporales)"
    )
    parser.add_argument(
        "--fecha-inicio",
        type=str,
        default="",
        help="Fecha de inicio en formato DD/MM/YYYY"
    )
    parser.add_argument(
        "--fecha-fin",
        type=str,
        default="",
        help="Fecha de fin en formato DD/MM/YYYY"
    )
    return parser.parse_args()

def extract_metadata_from_text(text: str, href: str, especialidad_label: str) -> dict:
    """
    Parsea los campos de metadatos del texto interno de la tarjeta de resolución.
    """
    # Extraer el UUID del enlace de descarga
    uuid = ""
    uuid_match = re.search(r"uuid=([^&]+)", href)
    if uuid_match:
        uuid = uuid_match.group(1)

    # Extraer expediente y tipo de documento (ej: Casación 001310-2022)
    # Buscamos el patrón de expediente XXXXXX-YYYY o XXXXX-YYYY
    nro_expediente = ""
    tipo_resolucion_header = ""
    
    exp_match = re.search(r"\b(\d{5,6}-\d{4})\b", text)
    if exp_match:
        nro_expediente = exp_match.group(1)
        # Extraer el tipo de documento del encabezado (antes del número)
        first_line = text.split('\n')[0].strip()
        header_match = re.search(r"^([A-Za-zñÑáéíóúÁÉÍÓÚ\s]+)", first_line)
        if header_match:
            tipo_resolucion_header = clean_string(header_match.group(1))

    # Helper para extraer campo con etiqueta
    def extract_field(label: str) -> str:
        pattern = r"{}\s*:\s*([^\n]+)".format(re.escape(label))
        match = re.search(pattern, text, re.IGNORECASE)
        return clean_string(match.group(1)) if match else ""

    # Extraer campos detallados de la tarjeta
    delito_pretension = extract_field("Pretensión/Delito") or extract_field("Pretensión / Delito")
    tipo_resolucion = extract_field("Tipo Resolución") or tipo_resolucion_header
    fecha_resolucion = extract_field("Fecha Resolución")
    sala_suprema = extract_field("Sala Suprema") or extract_field("Órgano Jurisdiccional")
    sumilla = extract_field("Sumilla")
    palabras_clave = extract_field("Palabras Clave")

    return {
        "uuid": uuid,
        "nro_expediente": nro_expediente,
        "tipo_resolucion": tipo_resolucion,
        "fecha_resolucion": fecha_resolucion,
        "sala_suprema": sala_suprema,
        "especialidad": especialidad_label,
        "delito_pretension": delito_pretension,
        "sumilla": sumilla,
        "palabras_clave": palabras_clave,
        "download_url": href
    }

async def scrape_search_results(page, especialidad_name: str, especialidad_val: str, anio: str, force: bool, fecha_inicio=None, fecha_fin=None):
    print(f"\n[SEEDER] Iniciando búsqueda: Especialidad={especialidad_name}, Año={anio}")
    
    # Helper to wait for RichFaces loading panelState
    async def wait_for_ajax():
        # Esperar a que el cargador aparezca si es lento (máx 500ms)
        try:
            await page.locator('#panelState').wait_for(state='visible', timeout=500)
        except:
            pass
        # Esperar a que el cargador y la sombra se oculten
        try:
            await page.locator('#panelState').wait_for(state='hidden', timeout=15000)
            await page.locator('#panelState_shade').wait_for(state='hidden', timeout=15000)
        except Exception as e:
            print(f"[SEEDER] Advertencia al esperar AJAX: {e}")
        await asyncio.sleep(0.5)

    # 1. Recargar el portal para limpiar sesiones viejas de JSF y evitar errores de vista
    await page.goto(PORTAL_URL, wait_until="networkidle", timeout=45000)
    await wait_for_ajax()

    # 2. Hacer clic en la pestaña "ESPECIALIZADA"
    try:
        tab_selector = '//span[text()="ESPECIALIZADA"]'
        await page.wait_for_selector(tab_selector, timeout=10000)
        await page.click(tab_selector)
        await wait_for_ajax()
    except Exception as e:
        print(f"[ERROR] No se pudo activar la pestaña ESPECIALIZADA: {e}")
        return

    # 3. Rellenar los filtros del formulario
    try:
        # Especialidad
        await page.select_option('#formBuscador\\:buEspecialidad', value=especialidad_val)
        await wait_for_ajax()
        
        # Año
        await page.select_option('#formBuscador\\:buAnio', value=anio)
        await wait_for_ajax()
    except Exception as e:
        print(f"[ERROR] Error al seleccionar los filtros del formulario: {e}")
        return

    # 4. Enviar formulario (Buscar)
    try:
        buscar_selector = '//div[contains(@id, ":especializada")]//input[@type="image" and contains(@src, "btn-buscar")]'
        await page.wait_for_selector(buscar_selector, timeout=8000)
        await page.click(buscar_selector)
        
        # Esperar la navegación a resultado.xhtml
        await page.wait_for_url("**/resultado.xhtml", timeout=20000)
        await wait_for_ajax()
    except Exception as e:
        print(f"[ERROR] Error al hacer clic en buscar: {e}")
        return

    # 5. Obtener el número total de resultados
    try:
        # Esperar a que aparezca el datascroller (indica que hay resultados)
        # o que aparezca el mensaje de cero resultados en el body
        try:
            await page.wait_for_selector(".rf-ds", timeout=8000)
            has_results = True
        except:
            has_results = False
            
        body_text = await page.inner_text("body")
        body_lower = body_text.lower()
        
        # Usar expresiones regulares con límites de palabra para evitar que "10 resultados" coincida con "0 resultados"
        is_empty = (
            "no se obtuvieron resultados" in body_lower or 
            "no se encontraron" in body_lower or 
            re.search(r"\b0\s+resultados\b", body_lower) is not None or
            not has_results
        )
        
        if is_empty:
            print(f"[SEEDER] 0 resultados encontrados para Especialidad={especialidad_name}, Año={anio}.")
            empty_file = TEMP_PAGES_DIR / f"tmp_{especialidad_name}_{anio}_empty.json"
            save_json(empty_file, [])
            return
        # Esperar al datascroller
        await page.wait_for_selector(".rf-ds", timeout=15000)
        
        body_content = await page.inner_text("body")
        count_match = re.search(r"se obtuvieron\s+([\d,.]+)\s+resultados", body_content, re.IGNORECASE)
        if not count_match:
            # Fallback a buscar cualquier indicación numérica antes de "resultados"
            count_match = re.search(r"([\d,.]+)\s+resultados\b", body_content, re.IGNORECASE)

        if count_match:
            total_results = int(count_match.group(1).replace(",", "").replace(".", ""))
            print(f"[SEEDER] Total de resultados encontrados: {total_results}")
        else:
            total_results = 10  # Fallback conservador
            print("[WARN] No se pudo parsear el número de resultados exacto, asumiendo paginación por defecto.")
            
    except Exception as e:
        # Verificar si realmente no hay resultados
        body_text = await page.inner_text("body")
        if "no se obtuvieron resultados" in body_text.lower() or "0 resultados" in body_text.lower():
            print(f"[SEEDER] 0 resultados para {especialidad_name} - {anio}")
            empty_file = TEMP_PAGES_DIR / f"tmp_{especialidad_name}_{anio}_empty.json"
            save_json(empty_file, [])
            return
        print(f"[ERROR] Error al determinar cantidad de resultados: {e}")
        return

    # Calcular total de páginas (RichFaces muestra 10 resultados por página)
    total_pages = math.ceil(total_results / 10)
    print(f"[SEEDER] Procesando {total_pages} páginas de resultados...")

    # 6. Iterar página por página
    for page_num in range(1, total_pages + 1):
        json_file = TEMP_PAGES_DIR / f"tmp_{especialidad_name}_{anio}_p{page_num}.json"
        
        # Verificar si la página ya fue procesada (Idempotencia)
        if json_file.exists() and not force:
            print(f"[SEEDER] Página {page_num}/{total_pages} ya existe localmente. Omitiendo raspado.")
            # Si no es la última página, debemos avanzar el paginador de todos modos
            if page_num < total_pages:
                await advance_page(page, page_num)
            continue

        print(f"[SEEDER] Raspando Página {page_num}/{total_pages}...")
        
        # Extraer elementos de la página actual
        try:
            # Seleccionar todos los enlaces de descarga directa
            download_links = page.locator('a[href*="ServletDescarga?uuid="]')
            link_count = await download_links.count()
            
            if link_count == 0:
                print(f"[WARN] No se encontraron enlaces de descarga en la página {page_num}.")
                # Guardamos un array vacío para no reintentar infinitamente
                save_json(json_file, [])
                if page_num < total_pages:
                    await advance_page(page, page_num)
                continue
                
            page_records = []
            
            # Utilizar JS evaluate en el navegador para extraer la tarjeta de forma robusta
            for i in range(link_count):
                try:
                    element_handle = await download_links.nth(i).element_handle()
                    href = await download_links.nth(i).get_attribute("href")
                    
                    card_data = await page.evaluate("""(link) => {
                        let container = link.closest('div');
                        // Subir en el árbol DOM hasta encontrar la tarjeta que contiene la metadata
                        while (container && !container.innerText.includes('Fecha Resolución') && container.parentElement) {
                            container = container.parentElement;
                        }
                        return container ? container.innerText : '';
                    }""", element_handle)
                    
                    if card_data:
                        record = extract_metadata_from_text(card_data, href, especialidad_name)
                        if record.get("uuid"):
                            # Filtrar por fecha si se especificó el rango
                            keep = True
                            if fecha_inicio or fecha_fin:
                                try:
                                    card_date = datetime.strptime(record.get("fecha_resolucion", ""), "%d/%m/%Y")
                                    if fecha_inicio and card_date < fecha_inicio:
                                        keep = False
                                    if fecha_fin and card_date > fecha_fin:
                                        keep = False
                                except Exception:
                                    pass
                            if keep:
                                page_records.append(record)
                except Exception as ex:
                    print(f"[WARN] Error al extraer tarjeta {i} de página {page_num}: {ex}")
            
            # Guardar registros de la página en un JSON temporal
            save_json(json_file, page_records)
            print(f"[SEEDER] Guardada página {page_num} con {len(page_records)} registros.")
            
        except Exception as e:
            print(f"[ERROR] Error al extraer registros de página {page_num}: {e}")

        # Avanzar a la siguiente página
        if page_num < total_pages:
            success = await advance_page(page, page_num)
            if not success:
                print("[ERROR] No se pudo avanzar a la siguiente página. Abortando loop de paginación.")
                break

async def advance_page(page, current_page_num: int) -> bool:
    """
    Avanza a la página siguiente pulsando el botón de página siguiente del DataScroller
    y esperando a que se cargue la nueva página.
    """
    try:
        # Encontrar el botón de siguiente página
        next_btn = page.locator('.rf-ds-btn-next').first
        if await next_btn.is_visible():
            await next_btn.click()
            # Esperar a que la página activa en el paginador cambie a current_page_num + 1
            expected_page = str(current_page_num + 1)
            
            # Usar wait_for_function para asegurar carga AJAX de la página esperada
            await page.wait_for_function(
                """(expected) => {
                    const active = document.querySelector('.rf-ds-act');
                    return active && active.innerText.trim() === expected;
                }""",
                arg=expected_page,
                timeout=12000
            )
            await asyncio.sleep(1.0) # Margen de seguridad para renderizado final de la tabla
            return True
        else:
            print("[SEEDER] Botón 'Siguiente' no visible.")
            return False
    except Exception as e:
        print(f"[ERROR] Excepción al intentar avanzar de página: {e}")
        return False

async def main():
    args = parse_arguments()
    
    target_especialidades = [e.strip() for e in args.especialidades.split(",") if e.strip()]
    
    fecha_inicio = None
    fecha_fin = None
    
    if args.fecha_inicio:
        try:
            fecha_inicio = datetime.strptime(args.fecha_inicio.strip(), "%d/%m/%Y")
        except Exception as e:
            print(f"[ERROR] Formato de fecha_inicio inválido: {args.fecha_inicio}. Debe ser DD/MM/YYYY.")
            
    if args.fecha_fin:
        try:
            fecha_fin = datetime.strptime(args.fecha_fin.strip(), "%d/%m/%Y")
        except Exception as e:
            print(f"[ERROR] Formato de fecha_fin inválido: {args.fecha_fin}. Debe ser DD/MM/YYYY.")
            
    # Si hay fechas de inicio/fin, recalcular los años dinámicamente
    if fecha_inicio or fecha_fin:
        start_year = fecha_inicio.year if fecha_inicio else 2021
        end_year = fecha_fin.year if fecha_fin else datetime.now().year
        target_anios = [str(y) for y in range(start_year, end_year + 1)]
    else:
        target_anios = [y.strip() for y in args.anios.split(",") if y.strip()]
        
    print("======================================================================")
    print("INICIANDO SEMBRADOR DE JURISPRUDENCIA (MÓDULO A)")
    print(f"Especialidades: {target_especialidades}")
    print(f"Años a escanear: {target_anios}")
    if fecha_inicio:
        print(f"Rango desde: {args.fecha_inicio}")
    if fecha_fin:
        print(f"Rango hasta: {args.fecha_fin}")
    print(f"Modo Headless: {args.headless}")
    print(f"Forzar sobrescritura: {args.force}")
    print("======================================================================")

    async with async_playwright() as p:
        # Lanzar Chromium con argumentos anti-detección
        browser = await p.chromium.launch(
            headless=args.headless,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        # Crear contexto aislado con viewport y user-agent realistas
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)  # Aplicar playwright-stealth
        
        # Regla de HSTS manual para redirigir peticiones HTTP a HTTPS
        async def handle_route(route):
            url = route.request.url
            if url.startswith("http://jurisprudencia.pj.gob.pe"):
                new_url = url.replace("http://", "https://")
                await route.fulfill(status=301, headers={"Location": new_url})
            else:
                await route.continue_()
                
        await page.route("**/*", handle_route)
        
        for esp_name in target_especialidades:
            if esp_name not in ESPECIALIDADES:
                print(f"[WARN] Especialidad '{esp_name}' no soportada. Omitiendo.")
                continue
            esp_val = ESPECIALIDADES[esp_name]
            
            for anio in target_anios:
                try:
                    await scrape_search_results(page, esp_name, esp_val, anio, args.force, fecha_inicio, fecha_fin)
                except Exception as ex:
                    print(f"[ERROR CRÍTICO] Excepción en loop de scraping para {esp_name} - {anio}: {ex}")
                    
        await browser.close()
        print("\n[SEEDER] Proceso de Sembrador Finalizado.")

if __name__ == "__main__":
    asyncio.run(main())
