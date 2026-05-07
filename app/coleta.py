"""Pipeline coleta -> classifica -> persiste -> verifica detalhe -> notifica.

Substitui o app/scheduler.py antigo (que tinha APScheduler in-process). Aqui
e tudo sincrono em fluxo CLI: o orquestrador externo (GitHub Actions cron)
chama `scripts/run_check.py` a cada 5 min.
"""

import asyncio
import logging
from typing import Optional

import httpx

from app.config import now_br, settings
from app.matchers.pipeline import classificar_e_filtrar
from app.notifier.dispatcher import enviar_evento
from app.notifier.rules import Evento, gerar_eventos, registrar_envio
from app.revalidator import revalidar_uma
from app.sources.registry import SOURCES
from app.store import Store


logger = logging.getLogger(__name__)


async def _verificar_antes_de_enviar(
    client: httpx.AsyncClient,
    store: Store,
    ev: Evento,
) -> tuple[bool, str]:
    """Re-checa a oferta no detalhe antes de notificar.

    Evita mandar pro Telegram oferta que ja virou SoldOut/OutOfStock entre a
    coleta da listagem e o envio. Side-effects no Store:
      - Se removida: ativa = False
      - Se preco mudou: atualiza preco_atual + desconto_pct + HistoricoPreco
                       e recalcula se ainda atende min_desconto_pct
    """
    oferta = store.get_oferta_by_id(ev.oferta_id)
    if not oferta:
        return False, "oferta sumiu do store"

    res = await revalidar_uma(client, oferta)
    acao = res["acao"]

    if acao == "remover":
        store.update_oferta(oferta["id"], ativa=False, atualizada_em=now_br())
        return False, f"encerrada ({res['motivo']})"

    if acao == "erro":
        return False, f"verif falhou ({res['motivo']})"

    if acao == "atualizar":
        novo = res["preco_novo"]
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

        if ev.tipo == "nova" and (novo_desconto or 0) < settings.min_desconto_pct:
            return False, (
                f"apos verif preco mudou pra R${novo:.2f}, "
                f"desconto {novo_desconto}% < {settings.min_desconto_pct}%"
            )

        ev.classificada.oferta.preco_atual = novo
        ev.classificada.oferta.desconto_pct = novo_desconto

    return True, "ok"


async def executar_coleta(store: Store, fonte_nome: Optional[str] = None) -> dict:
    """Executa coleta em todas as fontes registradas (ou em uma especifica).

    Retorna resumo {fonte: {brutas, classificadas, eventos, sucesso, erro}}.
    """
    resumo: dict[str, dict] = {}
    nomes = [fonte_nome] if fonte_nome else list(SOURCES.keys())

    for nome in nomes:
        if nome not in SOURCES:
            resumo[nome] = {"sucesso": False, "erro": "source nao registrada"}
            continue
        resumo[nome] = await _coletar_fonte(store, nome)
    return resumo


async def _coletar_fonte(store: Store, nome: str) -> dict:
    cls = SOURCES[nome]
    source = cls()
    try:
        brutas = await source.fetch()
        logger.info("[%s] %d brutas", nome, len(brutas))

        classificadas = classificar_e_filtrar(brutas)
        logger.info("[%s] %d classificadas (marcas-alvo)", nome, len(classificadas))

        eventos = gerar_eventos(classificadas, store)
        logger.info("[%s] %d eventos pra notificar", nome, len(eventos))

        enviados = 0
        descartados = 0
        if eventos:
            headers = {"User-Agent": settings.user_agent}
            async with httpx.AsyncClient(
                headers=headers, timeout=15.0, follow_redirects=True,
            ) as client:
                for ev in eventos:
                    deve, motivo = await _verificar_antes_de_enviar(client, store, ev)
                    await asyncio.sleep(settings.throttle_segundos)
                    if not deve:
                        descartados += 1
                        logger.info(
                            "[verify] skip oferta=%s tipo=%s motivo=%s",
                            ev.oferta_id, ev.tipo, motivo,
                        )
                        continue
                    sucesso, erro = await enviar_evento(ev)
                    registrar_envio(store, ev, sucesso, erro)
                    if sucesso:
                        enviados += 1
        logger.info(
            "[%s] enviados=%d descartados_pre_envio=%d",
            nome, enviados, descartados,
        )

        store.update_fonte(
            nome,
            ultima_coleta_em=now_br(),
            ultima_coleta_status="ok",
            ultima_coleta_erro=None,
            ultima_coleta_qtd=len(classificadas),
        )

        return {
            "sucesso": True,
            "brutas": len(brutas),
            "classificadas": len(classificadas),
            "eventos": len(eventos),
            "enviados": enviados,
            "descartados": descartados,
        }
    except Exception as e:
        logger.exception("Erro coletando %s", nome)
        store.update_fonte(
            nome,
            ultima_coleta_em=now_br(),
            ultima_coleta_status="erro",
            ultima_coleta_erro=str(e)[:500],
        )
        return {"sucesso": False, "erro": str(e)[:500]}
