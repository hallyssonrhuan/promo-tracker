"""Source: Pelando (pelando.com.br).

Estratégia 1 (principal): __NEXT_DATA__ com Apollo GraphQL cache.
  Pelando é Next.js + Apollo. O HTML embute __NEXT_DATA__ onde cada oferta
  aparece como "Offer:<id>" ou "Thread:<id>" no dicionário do Apollo cache.

Estratégia 2 (fallback): JSON-LD schema.org (igual ao Promobit).

User-Agent de navegador é necessário — Pelando bloqueia UAs de bot.
"""

import json
import logging
import re
from typing import Optional

import httpx
import hishel
from pathlib import Path

from app.config import settings
from app.sources.base import OfertaRaw, Source
from app.sources.promobit import AVAILABILITY_VALIDA, _REGEX_JSON_LD


logger = logging.getLogger(__name__)

URLS: dict[str, str] = {
    "tenis": "https://www.pelando.com.br/t/tenis",
    "calcados": "https://www.pelando.com.br/t/calcados",
    "esporte-e-lazer": "https://www.pelando.com.br/t/esporte-e-lazer",
    "maquiagem": "https://www.pelando.com.br/t/maquiagem",
    "cabelo": "https://www.pelando.com.br/t/cabelo",
    "calcados-infantis": "https://www.pelando.com.br/t/calcados-infantis",
    "roupa-infantil": "https://www.pelando.com.br/t/roupa-infantil",
}

_RE_NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(.+?)\s*</script>',
    re.DOTALL,
)

# Tipos GraphQL que representam uma oferta no Apollo cache
_TIPOS_OFERTA = ("Offer", "Thread", "Deal", "Post", "Promo")

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PelandoSource(Source):
    nome = "pelando"

    def _http_client(self):
        """User-Agent de navegador — Pelando bloqueia bots."""
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
            for slug, url in URLS.items():
                try:
                    html = await self._get(client, url)
                    self._save_last_html(slug, html)
                    items = self.parse_listagem(html)
                    ofertas.extend(items)
                    logger.info("[pelando] %s: %d ofertas", slug, len(items))
                except Exception as e:
                    logger.warning("[pelando] %s falhou: %s", slug, e)
        return ofertas

    def parse_listagem(self, html: str) -> list[OfertaRaw]:
        result = self._parse_next_data(html)
        if result:
            return result
        logger.debug("[pelando] __NEXT_DATA__ sem dados — tentando JSON-LD")
        return self._parse_jsonld(html)

    # ------------------------------------------------------------------ #
    #  Estratégia 1: __NEXT_DATA__ Apollo cache                           #
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
        apollo_state: dict = (
            page_props.get("apolloState")
            or page_props.get("__APOLLO_STATE__")
            or data.get("props", {}).get("__APOLLO_STATE__")
            or {}
        )
        if not isinstance(apollo_state, dict) or not apollo_state:
            return []

        merchants: dict[str, str] = {
            k: str(v.get("name") or v.get("displayName") or "?").strip()
            for k, v in apollo_state.items()
            if k.startswith("Merchant:") and isinstance(v, dict)
        }

        out: list[OfertaRaw] = []
        for key, val in apollo_state.items():
            if not isinstance(val, dict):
                continue
            tipo = val.get("__typename") or ""
            is_oferta = any(
                key.startswith(t + ":") or tipo == t
                for t in _TIPOS_OFERTA
            )
            if not is_oferta:
                continue
            oferta = self._parse_apollo_offer(val, merchants)
            if oferta:
                out.append(oferta)
        return out

    def _parse_apollo_offer(
        self, item: dict, merchants: dict[str, str]
    ) -> Optional[OfertaRaw]:
        titulo = (
            item.get("title") or item.get("name") or item.get("description") or ""
        ).strip()
        if not titulo:
            return None

        preco_raw = (
            item.get("price")
            or item.get("currentPrice")
            or item.get("dealPrice")
            or item.get("offerPrice")
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
            item.get("originalPrice")
            or item.get("oldPrice")
            or item.get("listPrice")
            or item.get("regularPrice")
            or item.get("msrp")
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

        url = (
            item.get("url")
            or item.get("shareUrl")
            or item.get("link")
            or item.get("href")
            or ""
        ).strip()
        if not url:
            offer_id = item.get("id") or item.get("threadId") or item.get("offerId")
            if offer_id:
                slug = (item.get("slug") or "").strip()
                url = f"https://www.pelando.com.br/oferta/{offer_id}"
                if slug:
                    url += f"/{slug}"
        if not url:
            return None
        if url.startswith("/"):
            url = "https://www.pelando.com.br" + url

        merchant_data = item.get("merchant") or item.get("store") or item.get("shop")
        loja = "?"
        if isinstance(merchant_data, dict):
            ref = merchant_data.get("__ref")
            if ref and ref in merchants:
                loja = merchants[ref]
            else:
                loja = (
                    merchant_data.get("name")
                    or merchant_data.get("displayName")
                    or "?"
                ).strip()
        elif isinstance(merchant_data, str):
            loja = merchant_data.strip() or "?"

        imgs = (
            item.get("images")
            or item.get("imageUrl")
            or item.get("image")
            or item.get("photo")
        )
        if isinstance(imgs, list):
            first = imgs[0] if imgs else None
            imagem_url = (
                first.get("url") or first.get("src")
                if isinstance(first, dict) else first
            )
        elif isinstance(imgs, str):
            imagem_url = imgs
        elif isinstance(imgs, dict):
            imagem_url = imgs.get("url") or imgs.get("src")
        else:
            imagem_url = None

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
    #  Estratégia 2: JSON-LD (fallback — igual ao Promobit)               #
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
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        oferta = self._parse_jsonld_product(item)
                        if oferta:
                            out.append(oferta)
            elif tipo == "Product":
                oferta = self._parse_jsonld_product(data)
                if oferta:
                    out.append(oferta)
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

        try:
            preco_de = float(offer.get("highPrice")) if offer.get("highPrice") else None
        except (TypeError, ValueError):
            preco_de = None
        if preco_de and preco_de <= preco_atual:
            preco_de = None
        if not preco_de:
            return None

        url = (offer.get("url") or "").strip()
        titulo = (item.get("name") or "").strip()
        if not titulo or not url:
            return None

        seller = offer.get("seller") or {}
        loja = (seller.get("name") or "?").strip() if isinstance(seller, dict) else "?"

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
