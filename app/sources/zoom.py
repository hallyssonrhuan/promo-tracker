"""Source: Zoom (zoom.com.br) — comparador de preços.

Estratégia: páginas de busca/categoria do Zoom têm JSON-LD com schema.org
Product/AggregateOffer onde lowPrice = melhor preço atual e highPrice =
preço mais alto entre as lojas (serve como preco_de).

Também tenta __NEXT_DATA__ se JSON-LD não der resultado.

Foco: buscas por marca+categoria (ex: "asics corrida") para maior precisão.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

import httpx
import hishel
from pathlib import Path

from app.config import settings
from app.sources.base import OfertaRaw, Source
from app.sources.promobit import AVAILABILITY_VALIDA, _REGEX_JSON_LD


logger = logging.getLogger(__name__)

# Buscas segmentadas por marca+categoria
BUSCAS: dict[str, str] = {
    # Tênis de corrida — marcas-alvo
    "asics-corrida": "asics tenis corrida",
    "mizuno-corrida": "mizuno wave tenis",
    "nike-corrida": "nike tenis corrida",
    "adidas-corrida": "adidas tenis corrida",
    "brooks-corrida": "brooks tenis corrida",
    "saucony-corrida": "saucony tenis",
    "olympikus-corrida": "olympikus tenis corrida",
    # Maquiagem
    "vizzela": "vizzela maquiagem",
    "dailus": "dailus maquiagem",
    # Cabelo
    "lola-cosmetics": "lola cosmetics shampoo",
    # Infantil
    "calcados-infantil": "tenis infantil menino 34 35 36",
}

_RE_NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(.+?)\s*</script>',
    re.DOTALL,
)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BASE_SEARCH = "https://www.zoom.com.br/busca/?q={query}"


def _build_url(query: str) -> str:
    return _BASE_SEARCH.format(query=quote_plus(query))


class ZoomSource(Source):
    nome = "zoom"

    def _http_client(self):
        headers = {
            "User-Agent": _BROWSER_UA,
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        common = dict(headers=headers, timeout=25.0, follow_redirects=True)
        if settings.dev_mode:
            storage = hishel.AsyncFileStorage(base_path=Path(settings.http_cache_dir))
            controller = hishel.Controller(force_cache=True, allow_stale=True)
            return hishel.AsyncCacheClient(storage=storage, controller=controller, **common)
        return httpx.AsyncClient(**common)

    async def fetch(self) -> list[OfertaRaw]:
        ofertas: list[OfertaRaw] = []
        async with self._http_client() as client:
            for slug, query in BUSCAS.items():
                url = _build_url(query)
                try:
                    html = await self._get(client, url)
                    self._save_last_html(slug, html)
                    items = self.parse_listagem(html)
                    ofertas.extend(items)
                    logger.info("[zoom] %s: %d ofertas", slug, len(items))
                except Exception as e:
                    logger.warning("[zoom] %s falhou: %s", slug, e)
        return ofertas

    def parse_listagem(self, html: str) -> list[OfertaRaw]:
        result = self._parse_jsonld(html)
        if result:
            return result
        return self._parse_next_data(html)

    # ------------------------------------------------------------------ #
    #  Estratégia 1: JSON-LD                                              #
    # ------------------------------------------------------------------ #

    def _parse_jsonld(self, html: str) -> list[OfertaRaw]:
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
                for li in data.get("itemListElement", []) or []:
                    item = li.get("item") if isinstance(li, dict) else None
                    if not isinstance(item, dict):
                        item = li  # alguns sites colocam o produto direto
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        oferta = self._parse_product(item)
                        if oferta:
                            out.append(oferta)
            elif tipo == "Product":
                oferta = self._parse_product(data)
                if oferta:
                    out.append(oferta)
        return out

    def _parse_product(self, item: dict) -> Optional[OfertaRaw]:
        titulo = (item.get("name") or "").strip()
        if not titulo:
            return None

        offers_raw = item.get("offers") or item.get("Offers")
        if not offers_raw:
            return None

        # Suporta Offer único, AggregateOffer e lista de Offer
        if isinstance(offers_raw, list):
            offer = offers_raw[0] if offers_raw else None
        else:
            offer = offers_raw  # dict (Offer ou AggregateOffer)
        if not isinstance(offer, dict):
            return None

        avail = offer.get("availability") or ""
        if avail and avail not in AVAILABILITY_VALIDA:
            return None

        # lowPrice = melhor preço (AggregateOffer) ou price (Offer)
        preco_raw = offer.get("lowPrice") or offer.get("price")
        if preco_raw is None:
            return None
        try:
            preco_atual = float(preco_raw)
        except (TypeError, ValueError):
            return None
        if preco_atual <= 0:
            return None

        # highPrice como preco_de (preço de referência = mais alto entre lojas)
        preco_de_raw = offer.get("highPrice") or offer.get("priceBeforeDiscount")
        try:
            preco_de = float(preco_de_raw) if preco_de_raw is not None else None
        except (TypeError, ValueError):
            preco_de = None
        if preco_de is not None and preco_de <= preco_atual:
            preco_de = None
        if not preco_de:
            return None

        desconto_pct = round((1 - preco_atual / preco_de) * 100)

        # URL — usa a URL do produto Zoom (detalhe tem JSON-LD pra revalidar)
        url = (item.get("url") or offer.get("url") or "").strip()
        if not url:
            return None
        if url.startswith("/"):
            url = "https://www.zoom.com.br" + url

        seller = offer.get("seller") or {}
        loja = (seller.get("name") or "Zoom").strip() if isinstance(seller, dict) else "Zoom"

        imgs = item.get("image") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        elif isinstance(imgs, dict):
            imgs = [imgs.get("url") or ""]
        imagem_url = imgs[0] if imgs else None

        return OfertaRaw(
            titulo=titulo,
            preco_atual=preco_atual,
            preco_de=preco_de,
            desconto_pct=desconto_pct,
            url=url,
            loja=loja,
            fonte=self.nome,
            imagem_url=imagem_url,
        )

    # ------------------------------------------------------------------ #
    #  Estratégia 2: __NEXT_DATA__                                        #
    # ------------------------------------------------------------------ #

    def _parse_next_data(self, html: str) -> list[OfertaRaw]:
        m = _RE_NEXT_DATA.search(html)
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []

        page_props = data.get("props", {}).get("pageProps", {})

        # Zoom pode ter produtos em "products", "items", "results" etc.
        produtos = (
            page_props.get("products")
            or page_props.get("items")
            or page_props.get("results")
            or page_props.get("offers")
            or []
        )
        if isinstance(produtos, dict):
            produtos = (
                produtos.get("products")
                or produtos.get("items")
                or produtos.get("data")
                or []
            )
        if not isinstance(produtos, list):
            return []

        out: list[OfertaRaw] = []
        for p in produtos:
            if not isinstance(p, dict):
                continue
            oferta = self._parse_next_product(p)
            if oferta:
                out.append(oferta)
        return out

    def _parse_next_product(self, p: dict) -> Optional[OfertaRaw]:
        titulo = (p.get("name") or p.get("title") or p.get("productName") or "").strip()
        if not titulo:
            return None

        preco_raw = (
            p.get("minPrice")
            or p.get("lowestPrice")
            or p.get("price")
            or p.get("currentPrice")
        )
        if preco_raw is None:
            return None
        try:
            preco_atual = float(preco_raw)
        except (TypeError, ValueError):
            return None
        if preco_atual <= 0:
            return None

        preco_de_raw = (
            p.get("maxPrice")
            or p.get("highestPrice")
            or p.get("originalPrice")
            or p.get("msrp")
        )
        try:
            preco_de = float(preco_de_raw) if preco_de_raw is not None else None
        except (TypeError, ValueError):
            preco_de = None
        if preco_de is not None and preco_de <= preco_atual:
            preco_de = None
        if not preco_de:
            return None

        desconto_pct = round((1 - preco_atual / preco_de) * 100)

        url = (p.get("url") or p.get("link") or p.get("href") or "").strip()
        if not url:
            return None
        if url.startswith("/"):
            url = "https://www.zoom.com.br" + url

        loja = (p.get("storeName") or p.get("seller") or p.get("merchant") or "Zoom").strip()
        if isinstance(loja, dict):
            loja = (loja.get("name") or "Zoom").strip()

        imgs = p.get("imageUrl") or p.get("image") or p.get("thumbnail") or ""
        imagem_url = imgs if isinstance(imgs, str) else None

        return OfertaRaw(
            titulo=titulo,
            preco_atual=preco_atual,
            preco_de=preco_de,
            desconto_pct=desconto_pct,
            url=url,
            loja=loja,
            fonte=self.nome,
            imagem_url=imagem_url,
        )
