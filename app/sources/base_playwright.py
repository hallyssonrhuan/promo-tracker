"""Base PlaywrightSource: renderiza JavaScript com Chromium headless.

Requer:
  pip install playwright
  playwright install chromium

Estratégia de extração (em ordem de prioridade):
  1. page.evaluate() para variáveis JS conhecidas (__NEXT_DATA__, __PRELOADED_STATE__, etc.)
  2. Busca heurística em qualquer estado JS encontrado
  3. JSON-LD (schema.org Product/ItemList) no HTML renderizado
  4. DOM scraping direto via Playwright evaluate() — detecta cards de produto por CSS
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from app.config import settings
from app.sources.base import OfertaRaw, Source, parse_preco_br
from app.sources.promobit import AVAILABILITY_VALIDA, _REGEX_JSON_LD


logger = logging.getLogger(__name__)

_PLAYWRIGHT_OK = False
try:
    from playwright.async_api import async_playwright, BrowserContext, Page
    _PLAYWRIGHT_OK = True
except ImportError:
    pass

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_JS_VARS = [
    "__NEXT_DATA__",
    "__PRELOADED_STATE__",
    "__APOLLO_STATE__",
    "__INITIAL_STATE__",
    "__REDUX_STATE__",
    "__STATE__",
]

# Caminhos de busca em __NEXT_DATA__ → lista de produtos
_NEXT_PATHS: list[tuple] = [
    ("props", "pageProps", "products"),
    ("props", "pageProps", "items"),
    ("props", "pageProps", "offers"),
    ("props", "pageProps", "search", "products"),
    ("props", "pageProps", "search", "items"),
    ("props", "pageProps", "search", "result", "products"),
    ("props", "pageProps", "resultSearch", "products"),
    ("props", "pageProps", "data", "products"),
    ("props", "pageProps", "data", "search", "products"),
    ("props", "pageProps", "data", "offers"),
    ("props", "pageProps", "initialData", "products"),
    ("props", "pageProps", "catalog", "products"),
    ("props", "pageProps", "searchResult", "products"),
    ("props", "pageProps", "pageData", "products"),
]

_REDUX_PATHS: list[tuple] = [
    ("catalog", "products"),
    ("products", "list"),
    ("search", "results"),
    ("search", "products"),
    ("listing", "products"),
]


def _dig(obj: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _is_product_list(lst: Any) -> bool:
    if not isinstance(lst, list) or not lst:
        return False
    for item in lst[:2]:
        if not isinstance(item, dict):
            return False
        keys = {str(k).lower() for k in item}
        if (keys & {"price", "bestprice", "lowprice", "saleprice", "valor", "preco"}) and \
           (keys & {"title", "name", "nome", "description", "titulo"}):
            return True
    return False


def _find_product_lists(obj: Any, depth: int = 4) -> list:
    if depth <= 0:
        return []
    if _is_product_list(obj):
        return [obj]
    if isinstance(obj, dict):
        found = []
        for v in obj.values():
            found.extend(_find_product_lists(v, depth - 1))
        return found
    return []


class PlaywrightSource(Source):
    """Source que usa Playwright para renderizar JavaScript antes de parsear."""

    URLS: dict[str, str] = {}
    _default_loja: str = "?"
    _base_url: str = ""
    _wait_selector: Optional[str] = None
    _nav_timeout: int = 30_000
    _idle_timeout: int = 8_000

    # ------------------------------------------------------------------ #
    #  Interface pública                                                   #
    # ------------------------------------------------------------------ #

    async def fetch(self) -> list[OfertaRaw]:
        if not _PLAYWRIGHT_OK:
            logger.warning(
                "[%s] playwright não encontrado — skip. Instale com:\n"
                "  pip install playwright && playwright install chromium",
                self.nome,
            )
            return []
        pages = await self._fetch_pages(self.URLS)
        ofertas: list[OfertaRaw] = []
        for slug, (html, js_state, dom_products) in pages.items():
            items = self.parse_pagina(html, js_state, dom_products)
            logger.info("[%s] %s: %d ofertas", self.nome, slug, len(items))
            ofertas.extend(items)
        return ofertas

    def parse_pagina(self, html: str, js_state: dict,
                     dom_products: Optional[list] = None) -> list[OfertaRaw]:
        # 1. JS state (__NEXT_DATA__, Redux, Apollo…)
        result = self._parse_from_js_state(js_state)
        if result:
            return result
        # 2. JSON-LD no HTML renderizado
        result = self._parse_jsonld_from_html(html)
        if result:
            return result
        # 3. DOM scraping direto (fallback final)
        if dom_products:
            return self._parse_dom_products(dom_products)
        return []

    # ------------------------------------------------------------------ #
    #  Playwright: lança browser, visita URLs, extrai estado JS           #
    # ------------------------------------------------------------------ #

    async def _fetch_pages(self, urls: dict[str, str]) -> dict[str, tuple]:
        """Retorna {slug: (html, js_state, dom_products)}."""
        result: dict[str, tuple] = {}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            ctx: BrowserContext = await browser.new_context(
                user_agent=_UA,
                viewport={"width": 1440, "height": 900},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
            )
            # Bloqueia mídia pesada para acelerar
            await ctx.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp,mp4,webm,woff,woff2,ttf,eot,ico}",
                lambda route, req: route.abort(),
            )
            try:
                for slug, url in urls.items():
                    async with self._semaforo:
                        page = await ctx.new_page()
                        try:
                            await page.goto(
                                url, wait_until="domcontentloaded",
                                timeout=self._nav_timeout,
                            )
                            if self._wait_selector:
                                try:
                                    await page.wait_for_selector(
                                        self._wait_selector, timeout=self._idle_timeout
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    await page.wait_for_load_state(
                                        "networkidle", timeout=self._idle_timeout
                                    )
                                except Exception:
                                    pass
                            # Aguarda renderização React extra
                            await page.wait_for_timeout(1500)
                            html = await page.content()
                            js_state = await self._extract_js_state(page)
                            dom_products = await self._scrape_dom_products(page)
                            if js_state:
                                logger.debug("[%s] %s: JS vars=%s", self.nome, slug,
                                             list(js_state.keys()))
                            if dom_products:
                                logger.debug("[%s] %s: dom cards=%d", self.nome, slug,
                                             len(dom_products))
                            result[slug] = (html, js_state, dom_products)
                            self._save_last_html(slug, html)
                        except Exception as e:
                            logger.warning("[%s] %s: %s", self.nome, slug, e)
                        finally:
                            await page.close()
                        await asyncio.sleep(settings.throttle_segundos)
            finally:
                await ctx.close()
                await browser.close()
        return result

    async def _extract_js_state(self, page) -> dict:
        state: dict = {}
        for var in _JS_VARS:
            try:
                val = await page.evaluate(f"() => window['{var}'] || null")
                if val and isinstance(val, dict):
                    state[var] = val
            except Exception:
                pass
        return state

    # ------------------------------------------------------------------ #
    #  Parsing: estado JS → OfertaRaw                                     #
    # ------------------------------------------------------------------ #

    def _parse_from_js_state(self, js_state: dict) -> list[OfertaRaw]:
        # 1. __NEXT_DATA__ com caminhos conhecidos
        nd = js_state.get("__NEXT_DATA__", {})
        if nd:
            result = self._parse_from_next_data(nd)
            if result:
                return result

        # 2. Redux / PRELOADED_STATE
        for var in ("__PRELOADED_STATE__", "__REDUX_STATE__", "__STATE__", "__INITIAL_STATE__"):
            redux = js_state.get(var, {})
            if redux:
                result = self._parse_from_redux(redux)
                if result:
                    return result

        # 3. Busca heurística em qualquer variável JS
        for var_data in js_state.values():
            for lst in _find_product_lists(var_data):
                products = self._parse_product_list(lst)
                if products:
                    return products
        return []

    def _parse_from_next_data(self, data: dict) -> list[OfertaRaw]:
        for path in _NEXT_PATHS:
            lst = _dig(data, *path)
            if lst is None:
                continue
            # GraphQL edges → nodes
            if isinstance(lst, list) and lst and isinstance(lst[0], dict):
                if "node" in lst[0]:
                    lst = [e["node"] for e in lst if isinstance(e, dict) and "node" in e]
                elif "edges" in lst[0]:
                    inner = lst[0]["edges"]
                    if isinstance(inner, list):
                        lst = [e.get("node", e) for e in inner if isinstance(e, dict)]
            products = self._parse_product_list(lst)
            if products:
                return products
        return []

    def _parse_from_redux(self, data: dict) -> list[OfertaRaw]:
        for path in _REDUX_PATHS:
            lst = _dig(data, *path)
            products = self._parse_product_list(lst)
            if products:
                return products
        return []

    def _parse_product_list(self, lst: Any) -> list[OfertaRaw]:
        if not isinstance(lst, list):
            return []
        return [o for item in lst if isinstance(item, dict) and (o := self._parse_generic_product(item))]

    def _parse_generic_product(self, item: dict) -> Optional[OfertaRaw]:
        titulo = (
            item.get("title") or item.get("name") or item.get("nome") or
            item.get("productName") or item.get("description") or ""
        ).strip()
        if not titulo:
            return None

        preco_atual = self._extract_preco(item, [
            "price", "bestPrice", "salePrice", "offerPrice", "lowPrice",
            "currentPrice", "minPrice", "valor",
            "price.value", "price.best", "price.current", "price.salePrice",
            "offers.lowPrice", "pricing.salePrice",
        ])
        if not preco_atual or preco_atual <= 0:
            return None

        preco_de = self._extract_preco(item, [
            "originalPrice", "regularPrice", "oldPrice", "highPrice",
            "listPrice", "fullPrice", "maxPrice", "msrp", "from",
            "price.originalPrice", "price.regularPrice", "price.listPrice",
            "price.from", "price.original",
            "offers.highPrice", "pricing.listPrice",
        ])
        if preco_de and preco_de <= preco_atual:
            preco_de = None
        if not preco_de:
            return None

        desconto_pct = round((1 - preco_atual / preco_de) * 100)
        url = self._extract_url(item)
        if not url:
            return None

        return OfertaRaw(
            titulo=titulo,
            preco_atual=preco_atual,
            preco_de=preco_de,
            desconto_pct=desconto_pct,
            url=url,
            loja=self._extract_loja(item),
            fonte=self.nome,
            imagem_url=self._extract_image(item),
        )

    def _extract_preco(self, item: dict, paths: list[str]) -> Optional[float]:
        for path in paths:
            parts = path.split(".")
            val: Any = item
            for part in parts:
                val = val.get(part) if isinstance(val, dict) else None
            if val is None:
                continue
            price = self._normalize_price(val)
            if price and price > 0:
                return price
        return None

    def _normalize_price(self, val: Any) -> Optional[float]:
        if isinstance(val, float):
            return val if val > 0 else None
        if isinstance(val, int):
            f = float(val)
            if f > 1_000:  # provavelmente centavos
                f /= 100
            return f if f > 0 else None
        if isinstance(val, str):
            return parse_preco_br(val)
        if isinstance(val, dict):
            for k in ("value", "amount", "best", "current", "final", "price", "cents"):
                if k in val:
                    return self._normalize_price(val[k])
        return None

    def _extract_url(self, item: dict) -> Optional[str]:
        raw = (
            item.get("url") or item.get("link") or item.get("href") or
            item.get("permalink") or item.get("productUrl") or
            item.get("canonicalUrl") or ""
        )
        if isinstance(raw, dict):
            raw = raw.get("href") or raw.get("url") or ""
        url = str(raw).strip()
        if not url:
            return None
        if url.startswith("/"):
            url = self._base_url + url
        return url if url.startswith("http") else None

    def _extract_loja(self, item: dict) -> str:
        seller = (
            item.get("seller") or item.get("merchant") or
            item.get("store") or item.get("brand") or {}
        )
        if isinstance(seller, dict):
            return (seller.get("name") or seller.get("nickname") or self._default_loja).strip()
        if isinstance(seller, str):
            return seller.strip() or self._default_loja
        return self._default_loja

    def _extract_image(self, item: dict) -> Optional[str]:
        img = (
            item.get("image") or item.get("imageUrl") or item.get("thumbnail") or
            item.get("photo") or item.get("imageUrls") or item.get("images")
        )
        if isinstance(img, list):
            img = img[0] if img else None
        if isinstance(img, dict):
            img = img.get("url") or img.get("src") or img.get("medium") or img.get("small")
        return str(img).strip() if isinstance(img, str) and img else None

    # ------------------------------------------------------------------ #
    #  Parsing: JSON-LD no HTML renderizado (fallback final)              #
    # ------------------------------------------------------------------ #

    def _parse_jsonld_from_html(self, html: str) -> list[OfertaRaw]:
        out: list[OfertaRaw] = []
        for m in _REGEX_JSON_LD.finditer(html):
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            tipo = data.get("@type")
            if tipo == "ItemList":
                for li in (data.get("itemListElement") or []):
                    node = li.get("item") if isinstance(li, dict) else li
                    if isinstance(node, dict) and node.get("@type") == "Product":
                        o = self._parse_jsonld_product(node)
                        if o:
                            out.append(o)
            elif tipo == "Product":
                o = self._parse_jsonld_product(data)
                if o:
                    out.append(o)
        return out

    def _parse_jsonld_product(self, item: dict) -> Optional[OfertaRaw]:
        ofs = item.get("offers") or []
        if isinstance(ofs, dict):
            ofs = [ofs]
        if not ofs:
            return None
        offer = ofs[0] if isinstance(ofs[0], dict) else None
        if not offer:
            return None

        avail = offer.get("availability") or ""
        if avail and avail not in AVAILABILITY_VALIDA:
            return None

        try:
            preco_atual = float(offer.get("price") or offer.get("lowPrice"))
        except (TypeError, ValueError):
            return None

        preco_de_raw = offer.get("highPrice") or offer.get("priceBeforeDiscount")
        try:
            preco_de = float(preco_de_raw) if preco_de_raw else None
        except (TypeError, ValueError):
            preco_de = None
        if preco_de and preco_de <= preco_atual:
            preco_de = None
        if not preco_de:
            return None

        titulo = (item.get("name") or "").strip()
        url = (offer.get("url") or item.get("url") or "").strip()
        if not titulo or not url:
            return None
        if url.startswith("/"):
            url = self._base_url + url

        seller = offer.get("seller") or {}
        loja = (seller.get("name") or self._default_loja) if isinstance(seller, dict) else self._default_loja

        imgs = item.get("image") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        imagem_url = imgs[0] if imgs else None

        return OfertaRaw(
            titulo=titulo,
            preco_atual=preco_atual,
            preco_de=preco_de,
            desconto_pct=round((1 - preco_atual / preco_de) * 100),
            url=url,
            loja=loja,
            fonte=self.nome,
            imagem_url=imagem_url,
        )

    # ------------------------------------------------------------------ #
    #  DOM scraping via page.evaluate() — fallback final                  #
    # ------------------------------------------------------------------ #

    async def _scrape_dom_products(self, page) -> list[dict]:
        """Extrai cards de produto via JavaScript evaluate no browser."""
        try:
            return await page.evaluate("""() => {
                const CARD_SELECTORS = [
                    '[data-testid*="product"]',
                    '[class*="ProductCard"]',
                    '[class*="product-card"]',
                    '[class*="productCard"]',
                    '[class*="product-item"]',
                    '[class*="shelf-item"]',
                    'li[class*="product"]',
                    'article[class*="product"]',
                    '[class*="CardProduct"]',
                    '[class*="item-product"]',
                ];
                const PRICE_SELECTORS = [
                    '[class*="price"]', '[class*="Price"]',
                    '[class*="valor"]', '[data-testid*="price"]',
                ];
                const TITLE_SELECTORS = [
                    '[data-testid*="title"]', '[data-testid*="name"]',
                    'h2', 'h3',
                    '[class*="title"]', '[class*="name"]',
                    '[class*="Title"]', '[class*="Name"]',
                ];

                let cards = [];
                for (const sel of CARD_SELECTORS) {
                    const found = Array.from(document.querySelectorAll(sel));
                    if (found.length > 2) { cards = found; break; }
                }

                const results = [];
                for (const card of cards.slice(0, 60)) {
                    try {
                        let titulo = '';
                        for (const sel of TITLE_SELECTORS) {
                            const el = card.querySelector(sel);
                            if (el && el.innerText && el.innerText.trim().length > 5) {
                                titulo = el.innerText.trim(); break;
                            }
                        }
                        if (!titulo) {
                            titulo = card.getAttribute('data-product-name') ||
                                     card.getAttribute('aria-label') || '';
                        }
                        if (!titulo || titulo.length < 5) continue;

                        const priceTexts = [];
                        for (const sel of PRICE_SELECTORS) {
                            for (const el of Array.from(card.querySelectorAll(sel))) {
                                const t = (el.innerText || '').trim();
                                if (t && (t.includes('R$') || /\d+[,\.]\d{2}/.test(t))) {
                                    priceTexts.push(t);
                                }
                            }
                        }

                        const anchor = card.querySelector('a[href]') || card.closest('a[href]');
                        const url = anchor ? anchor.href : '';
                        const img = card.querySelector('img');
                        const imageUrl = img ? (img.dataset.src || img.src || '') : '';

                        results.push({ titulo, priceTexts, url, imageUrl });
                    } catch (e) {}
                }
                return results;
            }""")
        except Exception as e:
            logger.debug("[%s] DOM scrape error: %s", self.nome, e)
            return []

    def _parse_dom_products(self, dom_products: list) -> list[OfertaRaw]:
        out: list[OfertaRaw] = []
        for item in dom_products:
            try:
                titulo = (item.get("titulo") or "").strip()
                url = (item.get("url") or "").strip()
                if not titulo or not url or not url.startswith("http"):
                    continue

                prices: list[float] = []
                for text in (item.get("priceTexts") or []):
                    for match in re.finditer(r"[\d][\d\.\,]*", text):
                        p = parse_preco_br(match.group(0))
                        if p and p > 0:
                            prices.append(p)

                prices = sorted(set(prices))
                if not prices:
                    continue

                preco_atual = prices[0]
                preco_de = prices[-1] if len(prices) > 1 and prices[-1] > preco_atual else None
                if not preco_de:
                    continue

                out.append(OfertaRaw(
                    titulo=titulo,
                    preco_atual=preco_atual,
                    preco_de=preco_de,
                    desconto_pct=round((1 - preco_atual / preco_de) * 100),
                    url=url,
                    loja=self._default_loja,
                    fonte=self.nome,
                    imagem_url=item.get("imageUrl") or None,
                ))
            except Exception as e:
                logger.debug("[%s] _parse_dom item error: %s", self.nome, e)
        return out
