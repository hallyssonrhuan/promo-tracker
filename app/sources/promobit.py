"""Source: Promobit (promobit.com.br).

Estratégia: o Promobit injeta um bloco JSON-LD ItemList no HTML com schema
Product/Offer (Schema.org) — dados estruturados pra Google. Isso e MUITO mais
estavel que parsear classes Tailwind aleatorias que mudam a cada deploy.

Cada categoria devolve ~10 produtos da pagina 1. Se quisermos mais, basta
adicionar ?p=2, ?p=3 nas URLs (paginacao).

Quando o Promobit mudar o schema (raro), olhar data/last_html/promobit_*.html
pra debug.
"""

import json
import logging
import re
from typing import Optional

from app.sources.base import OfertaRaw, Source


logger = logging.getLogger(__name__)


# Categorias que cobrem nossos nichos.
# O brand_filter / category_filter filtram pelo titulo, entao nao precisamos
# de URLs por marca (Promobit nao expoe paginas /marca/X estaveis).
# OBS: paginacao do Promobit e client-side, ?p=2 nao funciona — sempre vem
# os 10 mais recentes da categoria.
URLS: dict[str, str] = {
    # Tenis de corrida
    "calcados": "https://www.promobit.com.br/promocoes/calcados/s/",
    "calcados-masculinos": "https://www.promobit.com.br/promocoes/calcados-masculinos/s/",
    "esporte-e-lazer": "https://www.promobit.com.br/promocoes/esporte-e-lazer/",
    # Maquiagem
    "maquiagem": "https://www.promobit.com.br/promocoes/maquiagem/s/",
    # Cabelo (Lola)
    "shampoo": "https://www.promobit.com.br/promocoes/shampoo/s/",
    "condicionador": "https://www.promobit.com.br/promocoes/condicionador/s/",
    "creme-cabelo-leave-in": "https://www.promobit.com.br/promocoes/creme-cabelo-leave-in/s/",
    # Infantil masc
    "calcados-infantis": "https://www.promobit.com.br/promocoes/calcados-infantis/s/",
    "roupa-infantil": "https://www.promobit.com.br/promocoes/roupa-infantil/s/",
}


_REGEX_JSON_LD = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.+?)</script>',
    re.DOTALL,
)

# Schema.org availability values aceitos. Tudo fora disso (OutOfStock,
# Discontinued, SoldOut, etc.) e descartado no intake.
AVAILABILITY_VALIDA = {
    "https://schema.org/InStock",
    "https://schema.org/LimitedAvailability",
    # Em alguns lugares vem sem o prefixo
    "InStock",
    "LimitedAvailability",
}


class PromobitSource(Source):
    nome = "promobit"

    async def fetch(self) -> list[OfertaRaw]:
        ofertas: list[OfertaRaw] = []
        async with self._http_client() as client:
            for slug, url in URLS.items():
                try:
                    html = await self._get(client, url)
                    self._save_last_html(slug, html)
                    items = self.parse_listagem(html)
                    ofertas.extend(items)
                    logger.info("[promobit] %s: %d ofertas", slug, len(items))
                except Exception as e:
                    logger.warning("[promobit] %s falhou: %s", slug, e)
        return ofertas

    def parse_listagem(self, html: str) -> list[OfertaRaw]:
        out: list[OfertaRaw] = []
        for m in _REGEX_JSON_LD.finditer(html):
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("@type") != "ItemList":
                continue
            for li in data.get("itemListElement", []) or []:
                item = li.get("item") if isinstance(li, dict) else None
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue
                oferta = self._parse_product(item)
                if oferta:
                    out.append(oferta)
        return out

    def _parse_product(self, item: dict) -> Optional[OfertaRaw]:
        ofs = item.get("offers") or []
        if not ofs:
            return None
        offer = ofs[0] if isinstance(ofs[0], dict) else None
        if not offer:
            return None

        # Filtro 1: availability — descarta encerradas/sold out
        avail = offer.get("availability") or ""
        if avail and avail not in AVAILABILITY_VALIDA:
            return None

        preco_atual_raw = offer.get("price") or offer.get("lowPrice")
        if preco_atual_raw is None:
            return None
        try:
            preco_atual = float(preco_atual_raw)
        except (TypeError, ValueError):
            return None

        preco_de_raw = offer.get("highPrice")
        try:
            preco_de = float(preco_de_raw) if preco_de_raw is not None else None
        except (TypeError, ValueError):
            preco_de = None
        if preco_de is not None and preco_de <= preco_atual:
            preco_de = None

        # Filtro 2: desconto real — sem preco_de > preco_atual, nao e promocao
        if not preco_de:
            return None

        desconto_pct = round((1 - preco_atual / preco_de) * 100)

        url = (offer.get("url") or "").strip()
        if not url:
            return None
        titulo = (item.get("name") or "").strip()
        if not titulo:
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
            desconto_pct=desconto_pct,
            url=url,
            loja=loja,
            fonte=self.nome,
            imagem_url=imagem_url,
        )
