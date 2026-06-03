import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        # Manual HSTS rule to upgrade HTTP requests to HTTPS
        async def handle_route(route):
            url = route.request.url
            if url.startswith("http://jurisprudencia.pj.gob.pe"):
                new_url = url.replace("http://", "https://")
                print(f"[HSTS] Upgrading request via 301 Redirect: {url} -> {new_url}")
                await route.fulfill(status=301, headers={"Location": new_url})
            else:
                await route.continue_()
                
        await page.route("**/*", handle_route)
        
        print("1. Navegando al portal...")
        await page.goto("https://jurisprudencia.pj.gob.pe/jurisprudenciaweb/faces/page/inicio.xhtml", wait_until="networkidle")
        await asyncio.sleep(2)
        
        # Helper to wait for RichFaces loading panelState
        async def wait_for_ajax():
            print("Esperando AJAX...")
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
                print(f"Advertencia al esperar AJAX: {e}")
            await asyncio.sleep(0.5)

        # Depurar las pestañas de la página
        tabs_info = await page.evaluate("""() => {
            const elList = document.querySelectorAll('[id*="header"]');
            return Array.from(elList).map(el => ({
                id: el.id,
                tagName: el.tagName,
                className: el.className,
                style: el.getAttribute('style') || '',
                text: el.innerText
            }));
        }""")
        print("Pestañas encontradas:", tabs_info)
        
        await page.screenshot(path="step1_loaded.png")
        
        print("2. Haciendo clic en pestaña ESPECIALIZADA...")
        tab_lbl_selector = '//span[text()="ESPECIALIZADA"]'
        await page.wait_for_selector(tab_lbl_selector, timeout=10000)
        await page.click(tab_lbl_selector)
        await wait_for_ajax()
        await page.screenshot(path="step2_tab_clicked.png")
        
        print("3. Seleccionando filtros...")
        await page.select_option('#formBuscador\\:buEspecialidad', value="1") # Civil
        await wait_for_ajax()
        await page.select_option('#formBuscador\\:buAnio', value="2025") # 2025
        await wait_for_ajax()
        await page.screenshot(path="step3_filters_selected.png")
        
        print("4. Haciendo clic en Buscar...")
        buscar_selector = '//div[contains(@id, ":especializada")]//input[@type="image" and contains(@src, "btn-buscar")]'
        await page.click(buscar_selector)
        
        print("5. Esperando la navegación y resultados...")
        try:
            await page.wait_for_url("**/resultado.xhtml", timeout=20000)
            await page.wait_for_selector('.rf-ds', timeout=20000)
            print("Resultados cargados con éxito!")
        except Exception as e:
            print(f"Advertencia/Error al esperar resultados: {e}")
        await page.screenshot(path="step4_after_search.png")
        
        # Guardar el HTML completo
        html = await page.content()
        with open("page_content.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("HTML guardado en page_content.html")
        await browser.close()
        print("Prueba completada.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
