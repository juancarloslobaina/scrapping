from fastapi import FastAPI
from upstash_redis import Redis
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import json
import time
import random
import logging
import os

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar FastAPI y Redis
app = FastAPI()
redis = Redis.from_env()

# Tiempo máximo para que Cloudflare resuelva el challenge y aparezca la tabla de tasas
CHALLENGE_TIMEOUT_MS = 180000

# --- Lógica del Scraper (Turnstile Bypass y Extracción) ---

class TurnstileBypass:
    def __init__(self, headless=False):
        self.headless = headless
        
    def solve_turnstile(self, page, max_wait=30):
        """Intentar resolver Cloudflare Turnstile automáticamente"""
        logger.info("Buscando checkbox de Turnstile...")
        
        # Selectores para encontrar el checkbox de Turnstile
        turnstile_selectors = [
            'input[type="checkbox"]',
            '.cb-lb input',
            '[aria-label*="human"]',
            '[aria-label*="Verify"]',
            'iframe[src*="cloudflare"]',
            'iframe[src*="challenges"]'
        ]
        
        # Buscar iframe de Turnstile (común)
        iframes = page.query_selector_all('iframe')
        for iframe in iframes:
            src = iframe.get_attribute('src') or ''
            if 'cloudflare.com' in src or 'challenges.cloudflare.com' in src:
                logger.info(f"Encontrado iframe de Cloudflare: {src}")
                try:
                    # Cambiar al contexto del iframe
                    frame = iframe.content_frame()
                    if frame:
                        # Buscar checkbox dentro del iframe
                        checkbox = frame.query_selector('input[type="checkbox"]')
                        if checkbox:
                            # Simular movimiento humano hacia el checkbox
                            box = checkbox.bounding_box()
                            if box:
                                # Mover mouse lentamente hacia el checkbox
                                page.mouse.move(
                                    box['x'] + box['width']/2,
                                    box['y'] + box['height']/2,
                                    steps=random.randint(10, 20)
                                )
                                time.sleep(random.uniform(0.5, 1.5))
                                
                                # Hacer click
                                checkbox.click()
                                logger.info("Click en checkbox de Turnstile")
                                return self._wait_for_turnstile_success(page, frame, max_wait)
                except Exception as e:
                    logger.warning(f"Error con iframe: {e}")
        
        # Método 2: Buscar directamente en la página principal
        for selector in turnstile_selectors:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    logger.info(f"Elemento encontrado con selector: {selector}")
                    
                    # Scroll al elemento
                    element.scroll_into_view_if_needed()
                    
                    # Simular comportamiento humano
                    box = element.bounding_box()
                    if box:
                        # Movimiento de mouse humano
                        page.mouse.move(
                            box['x'] + random.uniform(10, box['width'] - 10),
                            box['y'] + random.uniform(10, box['height'] - 10),
                            steps=random.randint(15, 25)
                        )
                        time.sleep(random.uniform(0.3, 1.0))
                        
                        # Hacer click
                        element.click()
                        logger.info(f"Click en elemento: {selector}")
                        return True
            except:
                continue
        
        # Método 3: Usar JavaScript para interactuar con Shadow DOM
        logger.info("Intentando acceder via JavaScript...")
        try:
            # Intentar acceder al shadow DOM
            result = page.evaluate("""
                () => {
                    // Buscar elementos con shadow DOM
                    const elements = document.querySelectorAll('*');
                    for (let el of elements) {
                        if (el.shadowRoot) {
                            // Buscar checkbox en shadow DOM
                            const checkbox = el.shadowRoot.querySelector('input[type="checkbox"]');
                            if (checkbox) {
                                checkbox.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """)
            
            if result:
                logger.info("Click exitoso via JavaScript")
                return True
        except Exception as e:
            logger.warning(f"Error con JavaScript: {e}")
        
        # Método 4: Simular interacción con teclado (Tab + Enter)
        logger.info("Probando navegación por teclado...")
        try:
            # Presionar Tab varias veces para navegar
            for _ in range(random.randint(3, 8)):
                page.keyboard.press('Tab')
                time.sleep(random.uniform(0.1, 0.3))
            
            # Intentar Enter
            page.keyboard.press('Enter')
            time.sleep(2)
            
            # Verificar si hubo algún cambio
            return True
        except Exception as e:
            logger.warning(f"Error con teclado: {e}")
        
        return False
    
    def _wait_for_turnstile_success(self, page, frame=None, max_wait=30):
        """Esperar a que Turnstile se resuelva"""
        logger.info("Esperando resolución de Turnstile...")
        
        start_time = time.time()
        context = frame if frame else page
        
        while time.time() - start_time < max_wait:
            try:
                # Verificar indicadores de éxito
                success_indicators = [
                    "Success!",
                    "Verification complete",
                    "success",
                    "verified"
                ]
                
                # Buscar en texto visible
                page_text = page.content().lower()
                if any(indicator.lower() in page_text for indicator in success_indicators):
                    logger.info("Turnstile resuelto (texto encontrado)")
                    return True
                
                # Buscar elementos visuales de éxito
                success_selectors = [
                    '#success',
                    '.success',
                    '[aria-label*="success"]',
                    'svg.success',
                    '.cb-container[style*="display: block"]'
                ]
                
                for selector in success_selectors:
                    element = context.query_selector(selector)
                    if element and element.is_visible():
                        logger.info(f"Elemento de éxito encontrado: {selector}")
                        return True
                
                # Esperar un poco
                time.sleep(1)
                
            except Exception as e:
                logger.debug(f"Error verificando estado: {e}")
                time.sleep(1)
        
        logger.warning(f"Timeout después de {max_wait} segundos")
        return False
    
    def bypass_with_playwright(self, url):
        """Método principal para bypass"""
        
        with sync_playwright() as p:
            # Configuración stealth
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            )
            
            # Eliminar webdriver property
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = context.new_page()
            
            try:
                # Navegar a la URL
                logger.info(f"Navegando a {url}")
                page.goto(url, wait_until='networkidle', timeout=60000)
                
                # Verificar si hay Turnstile
                if self._detect_turnstile(page):
                    logger.info("Cloudflare Turnstile detectado")
                    
                    # Intentar resolver
                    if self.solve_turnstile(page):
                        logger.info("¡Turnstile resuelto exitosamente!")
                        
                        # Esperar a que la página cargue completamente
                        time.sleep(3)
                        
                        # Obtener contenido
                        content = page.content()
                        
                        return content
                    else:
                        logger.error("No se pudo resolver Turnstile")
                        return None
                else:
                    logger.info("No se detectó Turnstile")
                    return page.content()
                    
            except Exception as e:
                logger.error(f"Error: {e}")
                return None
            finally:
                browser.close()
    
    def _detect_turnstile(self, page):
        """Detectar si la página tiene Cloudflare Turnstile"""
        
        detection_patterns = [
            "Verify you are human",
            "Verifying...",
            "cloudflare/turnstile",
            "challenges.cloudflare.com",
            "cf-chl-widget",
            "turnstile"
        ]
        
        content = page.content().lower()
        
        # Verificar por patrones de texto
        for pattern in detection_patterns:
            if pattern.lower() in content:
                return True
        
        # Verificar por iframes específicos
        iframes = page.query_selector_all('iframe')
        for iframe in iframes:
            src = iframe.get_attribute('src') or ''
            if any(pattern in src.lower() for pattern in ['cloudflare', 'challenges', 'turnstile']):
                return True
        
        # Verificar por elementos específicos
        turnstile_elements = [
            'input[type="checkbox"][aria-label*="human"]',
            '.cb-lb',
            '#SoGDz7',
            '[id*="turnstile"]',
            '[class*="turnstile"]'
        ]
        
        for selector in turnstile_elements:
            if page.query_selector(selector):
                return True
        
        return False

# Uso alternativo: Usando espera inteligente
def intelligent_turnstile_bypass(url):
    """Enfoque más inteligente para bypass"""
    
    with sync_playwright() as p:
        # headless=True es importante para Vercel
        browser = p.chromium.launch(headless=True)
        
        # Contexto con más configuración stealth
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            geolocation={'latitude': 40.7128, 'longitude': -74.0060},
        )
        
        # Scripts de stealth avanzados
        context.add_init_script("""
            // Eliminar rastros de automatización
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            
            // Sobrescribir permisos
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Mock Chrome runtime
            window.chrome = { runtime: {} };
        """)
        
        page = context.new_page()
        
        # Headers realistas
        page.set_extra_http_headers({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        try:
            # Navegar (la espera real es por la tabla de tasas, más abajo)
            response = page.goto(url, wait_until='domcontentloaded', timeout=60000)
            # Un 403 con cf-mitigated=challenge indica que Cloudflare mostró el challenge
            if response:
                logger.info(f"Respuesta inicial: HTTP {response.status}, cf-mitigated={response.headers.get('cf-mitigated')}")

            # Estrategia 1: Esperar a que Cloudflare resuelva el challenge y cargue la tabla de tasas.
            # Con poca CPU (Render free: 0.1 CPU) el challenge tarda mucho más que en local,
            # así que una espera fija de pocos segundos devuelve la página "Just a moment..."
            logger.info("Esperando a que se resuelva el challenge y cargue la tabla de tasas...")
            start_time = time.time()
            try:
                page.wait_for_selector('div.watermark tr', state='attached', timeout=CHALLENGE_TIMEOUT_MS)
                logger.info(f"Tabla de tasas cargada en {time.time() - start_time:.0f}s")
            except PlaywrightTimeoutError:
                logger.warning(f"La tabla de tasas no cargó en {CHALLENGE_TIMEOUT_MS // 1000}s (título: {page.title()!r})")

            # Estrategia 2: Scroll para activar scripts
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(2000)
            
            # Obtener contenido final
            content = page.content()            
            
            return content
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return None
        finally:
            browser.close()

# Uso con diferentes estrategias
def multi_strategy_bypass(url):
    """Probamos múltiples estrategias"""
    return intelligent_turnstile_bypass(url)

def describe_page(html):
    """
    Resume la página recibida para diagnosticar por qué no se extrajeron monedas.
    """
    soup = BeautifulSoup(html, 'html.parser')
    titulo = soup.title.get_text(strip=True) if soup.title else None

    # Marcas que solo aparecen en la página de challenge de Cloudflare ("Just a moment...")
    challenge_cloudflare = '_cf_chl_opt' in html or (titulo or '').lower().startswith('just a moment')

    return {
        "titulo": titulo,
        "tamano_html": len(html),
        "challenge_cloudflare": challenge_cloudflare,
        "watermarks": len(soup.select('div.watermark')),
        "tablas": len(soup.find_all('table')),
        "texto_inicio": soup.body.get_text(" ", strip=True)[:300] if soup.body else None
    }

def extract_currency_data(html):
    """
    Extrae datos de monedas eliminando duplicados.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Acotar al contenedor watermark de la tabla de tasas para evitar falsos positivos
    # La página repite la tabla (escritorio y móvil); tomamos el primer watermark que contiene filas
    watermark_elems = soup.select('div.watermark')
    watermark_elem = None
    for wm in watermark_elems:
        if wm.find('tr'):
            watermark_elem = wm
            break

    if not watermark_elem:
        logger.warning("No se encontró ningún elemento <div class='watermark'> que contenga filas (tr)")
        return {
            "origen": "eltoque.com",
            "fecha_actualizacion": None,
            "pais": "CUBA",
            "monedas": [],
            "estadisticas": {"total_monedas_unicas": 0, "total_filas_encontradas": 0}
        }


    # Buscar solo dentro del watermark
    all_rows = watermark_elem.find_all('tr')
    logger.info(f"Total de filas encontradas en el HTML: {len(all_rows)}")

    # La moneda ("1 USD") va en el span del tooltip; el otro span es la descripción ("Dólar Estadounidense")
    currency_selector = '.tooltip-host > span:not([role="tooltip"])'
    currency_rows = [
        row for row in all_rows
        if row.select_one(currency_selector)
    ]

    currency_dict = {}
    currency_data = []

    for row in currency_rows:
        currency_elem = row.select_one(currency_selector)
        price_elem = row.select_one('span.font-extrabold.text-lg.leading-tight')

        if not currency_elem or not price_elem:
            continue

        currency_text = currency_elem.get_text(strip=True)
        parts = currency_text.split(None, 1)
        cantidad = parts[0] if len(parts) > 0 else "1"
        moneda = parts[1] if len(parts) > 1 else currency_text

        precio_text = price_elem.get_text(strip=True).replace('CUP', '').strip()

        clave = f"{moneda}_{precio_text}"
        if clave in currency_dict:
            continue
        currency_dict[clave] = True

        price_classes = price_elem.get('class', [])
        if 'text-red-600' in price_classes:
            tendencia = "sube"
        elif 'text-emerald-600' in price_classes:
            tendencia = "baja"
        else:
            tendencia = "neutral"

        # Acotado al contenedor del precio: el tooltip de la moneda también es un span.inline-flex
        change_elem = price_elem.parent.select_one('span.inline-flex span:last-child')
        cambio_valor = change_elem.get_text(strip=True) if change_elem else None

        try:
            precio_cup = float(precio_text) if '.' in precio_text else int(precio_text)
        except ValueError:
            logger.warning(f"No se pudo convertir precio: {precio_text}")
            continue

        currency_data.append({
            "moneda": moneda,
            "cantidad": cantidad,
            "precio_cup": precio_cup,
            "tendencia": tendencia,
            "cambio": cambio_valor
        })

    # La fecha está en el pie de la tarjeta de tasas, fuera del watermark pero en su mismo contenedor
    time_elem = watermark_elem.parent.find('time') or soup.find('time')
    hora_elem = soup.select_one('.time')
    pais_elem = soup.select_one('.country')

    fecha_actualizacion = None
    if time_elem:
        fecha_actualizacion = time_elem.get('datetime') or time_elem.get_text(strip=True)

    return {
        "origen": "eltoque.com",
        "fecha_actualizacion": fecha_actualizacion,
        "pais": pais_elem.get_text(strip=True) if pais_elem else "CUBA",
        "monedas": currency_data,
        "estadisticas": {
            "total_monedas_unicas": len(currency_data),
            "total_filas_encontradas": len(currency_rows)
        }
    }

# --- Endpoints de la API ---

@app.get("/api/data")
def get_data():
    """
    Retrieves data from Upstash Redis.
    """
    try:
        data_str = redis.get("cron_data")
        if data_str is None:
            return {"message": "No data found. The cron job may not have run yet."}
        # upstash-redis can return bytes, so we decode it before parsing JSON
        if isinstance(data_str, bytes):
            data_str = data_str.decode('utf-8')
        return json.loads(data_str)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/cron")
def job_execution():
    """
    This function is executed by the Vercel cron job.
    It runs the scraper, extracts data, and stores it in Upstash Redis.
    """
    url = "https://eltoque.com"
    
    try:
        logger.info("Iniciando ejecución del Cron Job...")
        
        # 1. Ejecutar el scraper (Bypass de Cloudflare)
        content = multi_strategy_bypass(url)
        
        if content:
            # 2. Extraer datos procesados
            data = extract_currency_data(content)
            
            # 3. Guardar en Upstash Redis (Reemplaza save_to_json local)
            redis.set("cron_data", json.dumps(data))

            logger.info(f"Cron ejecutado exitosamente. {len(data.get('monedas', []))} monedas procesadas.")
            result = {
                "message": "Cron executed successfully",
                "status": "success",
                "updated_at": data.get("fecha_actualizacion"),
                "count": len(data.get("monedas", []))
            }

            # Sin monedas: reportar qué página llegó y guardar el HTML 24h para revisarlo
            if not data.get("monedas"):
                diagnostico = describe_page(content)
                logger.warning(f"No se extrajeron monedas. Diagnóstico: {json.dumps(diagnostico, ensure_ascii=False)}")
                try:
                    redis.set("cron_debug_html", content, ex=86400)
                    diagnostico["html_guardado_en"] = "cron_debug_html"
                except Exception as e:
                    logger.warning(f"No se pudo guardar el HTML de diagnóstico: {e}")
                result["diagnostico"] = diagnostico

            return result
        else:
            logger.error("No se pudo obtener contenido del scraper.")
            return {"message": "Scraping failed", "status": "error", "error": "No content received from scraper"}
            
    except Exception as e:
        logger.error(f"Excepción en el cron job: {e}")
        return {"message": "Cron execution failed", "error": str(e)}
