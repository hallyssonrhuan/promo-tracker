"""Source: Mercado Livre (mercadolivre.com.br) via API pública.

Usa a API REST pública do ML — não precisa de Playwright.
Endpoint: https://api.mercadolibre.com/sites/MLB/search

O campo `original_price` só é preenchido quando há desconto real,
tornando a filtragem muito confiável (preço de referência verídico).
"""

import logging
from typing import Optional
from urllib.parse import quote_plus

from app.sources.base import OfertaRaw, Source


logger = logging.getLogger(__name__)

_BASE = "https://api.mercadolibre.com/sites/MLB/search"
_LIMIT = 50

BUSCAS: dict[str, str] = {
    # Tênis de corrida — marcas-alvo
    "asics-corrida": "asics tenis corrida",
    "mizuno-corrida": "mizuno wave tenis",
    "nike-corrida": "nike tenis corrida",
    "adidas-corrida": "adidas ultraboost corrida",
    "brooks-corrida": "brooks tenis corrida",
    "saucony": "saucony tenis",
    "olympikus": "olympikus tenis corrida",
    "fila-corrida": "fila tenis corrida",
    # Maquiagem
    "vizzela": "vizzela maquiagem",
    "dailus": "dailus maquiagem",
    # Cabelo
    "lola-cosmetics": "lola cosmetics shampoo",
    # Infantil masc
    "tenis-infantil-34": "tenis infantil menino tam 34",
    "tenis-infantil-35": "tenis infantil menino tam 35",
    "tenis-infantil-36": "tenis infantil menino tam 36",
    "roupa-infantil-10": "camiseta menino 10 anos",
    "roupa-infantil-12": "bermuda menino 12 anos",
}


def _build_url(query: str) -> str:
    return f"{_BASE}?q={quote_plus(query)}&limit={_LIMIT}&condition=new"


class MercadoLivreSource(Source):
    nome = "mercadolivre"

    async def fetch(self) -> list[OfertaRaw]:
        ofertas: list[OfertaRaw] = []
        async with self._http_client() as client:
            for slug, query in BUSCAS.items():
                url = _build_url(query)
                try:
                    resp_text = await self._get(client, url)
                    import json
                    data = json.loads(resp_text)
                    items = self._parse_results(data.get("results") or [])
                    ofertas.extend(items)
                    logger.info("[mercadolivre] %s: %d ofertas", slug, len(items))
                except Exception as e:
                    logger.warning("[mercadolivre] %s falhou: %s", slug, e)
        return ofertas

    def _parse_results(self, results: list) -> list[OfertaRaw]:
        out = []
        for item in results:
            o = self._parse_item(item)
            if o:
                out.append(o)
        return out

    def _parse_item(self, item: dict) -> Optional[OfertaRaw]:
        titulo = (item.get("title") or "").strip()
        if not titulo:
            return None

        preco_atual_raw = item.get("price")
        if preco_atual_raw is None:
            return None
        try:
            preco_atual = float(preco_atual_raw)
        except (TypeError, ValueError):
            return None
        if preco_atual <= 0:
            return None

        # original_price só está preenchido quando há desconto real
        preco_de_raw = item.get("original_price")
        if preco_de_raw is None:
            return None
        try:
            preco_de = float(preco_de_raw)
        except (TypeError, ValueError):
            return None
        if preco_de <= preco_atual:
            return None

        desconto_pct = round((1 - preco_atual / preco_de) * 100)

        url = (item.get("permalink") or "").strip()
        if not url:
            return None

        seller = item.get("seller") or {}
        loja = (seller.get("nickname") or "Mercado Livre").strip()

        # ML thumbnail: pequeno, substitui por versão maior
        thumbnail = item.get("thumbnail") or ""
        imagem_url = thumbnail.replace("I.jpg", "O.jpg") if thumbnail else None

        qty = item.get("available_quantity") or 0
        if isinstance(qty, int) and qty == 0:
            return None

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
