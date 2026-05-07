"""Revalidacao em tempo real: re-checa cada Oferta ativa.

Pra cada oferta:
  - GET URL (com timeout). Se 404 -> ativa=False ("removida")
  - Senao: parse JSON-LD do detalhe -> extrai availability + price.
  - Se availability != InStock/LimitedAvailability -> ativa=False ("encerrada")
  - Se preco mudou:
      - sempre adiciona HistoricoPreco
      - atualiza preco_atual + atualizada_em
      - se queda >= QUEDA_MIN_PCT -> emite Evento "baixou" pra notificar

Roda em sequencia com a coleta no script run_check.py.

NAO usa cache HTTP (precisa do dado fresco) — cliente httpx puro.
"""

import asyncio
import json
import logging
import re
from typing import Optional

import httpx

from app.config import now_br, settings
from app.matchers.pipeline import OfertaClassificada
from app.notifier.dispatcher import enviar_evento
from app.notifier.rules import Evento, registrar_envio
from app.sources.base import OfertaRaw
from app.sources.promobit import AVAILABILITY_VALIDA, _REGEX_JSON_LD
from app.store import Store


logger = logging.getLogger(__name__)


# Queda minima entre o preco anterior e o novo pra disparar evento "baixou"
QUEDA_MIN_PCT = 5.0


def parse_oferta_detail(html: str) -> Optional[dict]:
    """Extrai do detalhe Promobit: {price, availability}."""
    for m in _REGEX_JSON_LD.finditer(html):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not (isinstance(data, dict) and data.get("@type") == "Product"):
            continue
        offers = data.get("offers")
        if isinstance(offers, dict):
            inner = offers.get("offers")
            if isinstance(inner, list) and inner:
                offer = inner[0]
            else:
                offer = offers
        elif isinstance(offers, list) and offers:
            offer = offers[0]
        else:
            continue
        if not isinstance(offer, dict):
            continue
        try:
            price = float(offer.get("price") or offer.get("lowPrice"))
        except (TypeError, ValueError):
            continue
        return {
            "price": price,
            "availability": offer.get("availability") or "",
        }
    return None


async def revalidar_uma(client: httpx.AsyncClient, oferta: dict) -> dict:
    """Retorna {acao, preco_anterior?, preco_novo?, motivo?}.

    `oferta` e o dict do Store (tem 'url', 'preco_atual', 'id').
    """
    try:
        r = await client.get(oferta["url"])
    except Exception as e:
        return {"acao": "erro", "motivo": f"http: {e}"}

    if r.status_code == 404:
        return {"acao": "remover", "motivo": "404"}
    if r.status_code >= 400:
        return {"acao": "erro", "motivo": f"http {r.status_code}"}

    parsed = parse_oferta_detail(r.text)
    if not parsed:
        return {"acao": "erro", "motivo": "json-ld nao encontrado"}

    if parsed["availability"] and parsed["availability"] not in AVAILABILITY_VALIDA:
        return {"acao": "remover", "motivo": f"availability={parsed['availability'].split('/')[-1]}"}

    novo = parsed["price"]
    anterior = oferta["preco_atual"]
    if abs(novo - anterior) < 0.01:
        return {"acao": "manter"}
    return {"acao": "atualizar", "preco_anterior": anterior, "preco_novo": novo}


async def revalidar_ofertas_ativas(store: Store) -> dict:
    """Roda revalidacao em todas Ofertas ativas. Atualiza/remove + notifica quedas."""
    resumo = {"checadas": 0, "removidas": 0, "atualizadas": 0, "notif_enviadas": 0, "erros": 0}

    headers = {"User-Agent": settings.user_agent}

    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
        ofertas = store.list_ofertas_ativas()
        logger.info("[revalidator] %d ofertas ativas pra checar", len(ofertas))

        for oferta in ofertas:
            res = await revalidar_uma(client, oferta)
            await asyncio.sleep(settings.throttle_segundos)

            resumo["checadas"] += 1
            acao = res["acao"]

            if acao == "remover":
                store.update_oferta(oferta["id"], ativa=False, atualizada_em=now_br())
                resumo["removidas"] += 1
                logger.info("[revalidator] removida #%d (%s)", oferta["id"], res["motivo"])

            elif acao == "atualizar":
                novo = res["preco_novo"]
                anterior = res["preco_anterior"]
                preco_de = oferta.get("preco_de")
                novo_desconto = (
                    round((1 - novo / preco_de) * 100) if preco_de else oferta.get("desconto_pct")
                )
                store.update_oferta(
                    oferta["id"],
                    preco_atual=novo,
                    desconto_pct=novo_desconto,
                    atualizada_em=now_br(),
                )
                store.add_historico(oferta["id"], novo, now_br())
                resumo["atualizadas"] += 1

                # Disparar "baixou" se queda significativa
                if novo < anterior:
                    queda = (1 - novo / anterior) * 100
                    if queda >= QUEDA_MIN_PCT:
                        atualizada = store.get_oferta_by_id(oferta["id"])
                        await _notificar_queda(store, atualizada, anterior, resumo)

            elif acao == "erro":
                resumo["erros"] += 1
                logger.warning("[revalidator] #%d erro: %s", oferta["id"], res["motivo"])

    return resumo


async def _notificar_queda(store: Store, oferta: dict,
                           preco_anterior: float, resumo: dict) -> None:
    produto = store.get_produto_by_id(oferta["produto_id"])
    if not produto:
        return
    raw = OfertaRaw(
        titulo=produto["titulo_original"],
        preco_atual=oferta["preco_atual"],
        preco_de=oferta.get("preco_de"),
        desconto_pct=oferta.get("desconto_pct"),
        url=oferta["url"],
        loja=oferta["loja"],
        fonte="revalidator",
        imagem_url=produto.get("imagem_url"),
    )
    classif = OfertaClassificada(
        oferta=raw, marca=produto["marca"], categoria=produto["categoria"],
    )
    evento = Evento(
        classificada=classif, tipo="baixou",
        oferta_id=oferta["id"], preco_anterior=preco_anterior,
    )
    sucesso, erro = await enviar_evento(evento)
    registrar_envio(store, evento, sucesso, erro)
    if sucesso:
        resumo["notif_enviadas"] += 1
