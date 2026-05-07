"""Testa revalidator: parser de detalhe + acao por oferta + job completo."""

from pathlib import Path

import httpx
import pytest

from app.matchers.pipeline import OfertaClassificada
from app.notifier.rules import gerar_eventos
from app.revalidator import (
    parse_oferta_detail, revalidar_uma, revalidar_ofertas_ativas,
)
from app.sources.base import OfertaRaw


FIX = Path(__file__).parent / "fixtures"


# ---------- parse_oferta_detail ----------

def test_parse_detalhe_ativa():
    html = (FIX / "promobit_oferta_detail_ativa.html").read_text(encoding="utf-8")
    res = parse_oferta_detail(html)
    assert res == {"price": 539.90, "availability": "https://schema.org/InStock"}


def test_parse_detalhe_encerrada():
    html = (FIX / "promobit_oferta_detail_encerrada.html").read_text(encoding="utf-8")
    res = parse_oferta_detail(html)
    assert res == {"price": 539.90, "availability": "https://schema.org/OutOfStock"}


def test_parse_detalhe_html_invalido():
    assert parse_oferta_detail("<html></html>") is None


# ---------- revalidar_uma (com httpx mock) ----------

@pytest.fixture
def store_com_oferta(store):
    """Persiste 1 oferta classificada de Asics no store."""
    oc = OfertaClassificada(
        oferta=OfertaRaw(
            titulo="Tenis Asics Gel-Cumulus 26", preco_atual=600, preco_de=800,
            desconto_pct=25, url="https://promobit.com/oferta/1",
            loja="Centauro", fonte="promobit",
        ),
        marca="Asics", categoria="corrida",
    )
    gerar_eventos([oc], store)
    oferta = next(iter(store.raw()["ofertas"].values()))
    return store, oferta


async def _client_com_resposta(status: int, html: str) -> httpx.AsyncClient:
    def handler(request):
        return httpx.Response(status, html=html)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_revalidar_uma_404_retorna_remover(store_com_oferta):
    _, oferta = store_com_oferta
    async with await _client_com_resposta(404, "") as client:
        res = await revalidar_uma(client, oferta)
    assert res == {"acao": "remover", "motivo": "404"}


async def test_revalidar_uma_encerrada(store_com_oferta):
    _, oferta = store_com_oferta
    html = (FIX / "promobit_oferta_detail_encerrada.html").read_text(encoding="utf-8")
    async with await _client_com_resposta(200, html) as client:
        res = await revalidar_uma(client, oferta)
    assert res["acao"] == "remover"
    assert "OutOfStock" in res["motivo"]


async def test_revalidar_uma_preco_igual_mantem(store_com_oferta):
    _, oferta = store_com_oferta
    oferta["preco_atual"] = 539.90
    html = (FIX / "promobit_oferta_detail_ativa.html").read_text(encoding="utf-8")
    async with await _client_com_resposta(200, html) as client:
        res = await revalidar_uma(client, oferta)
    assert res == {"acao": "manter"}


async def test_revalidar_uma_preco_mudou_atualiza(store_com_oferta):
    _, oferta = store_com_oferta
    # oferta tem preco_atual=600, fixture diz 539.90
    html = (FIX / "promobit_oferta_detail_ativa.html").read_text(encoding="utf-8")
    async with await _client_com_resposta(200, html) as client:
        res = await revalidar_uma(client, oferta)
    assert res["acao"] == "atualizar"
    assert res["preco_anterior"] == 600
    assert res["preco_novo"] == 539.90


# ---------- revalidar_ofertas_ativas (job completo) ----------

@pytest.fixture
def patched_revalidator(monkeypatch):
    """Mocka send_message e zera throttle pra acelerar."""
    from app import revalidator as rev_mod
    monkeypatch.setattr(rev_mod.settings, "throttle_segundos", 0)

    enviadas = []

    async def fake_dispatch(evento):
        from app.notifier.telegram import format_evento_html
        enviadas.append(format_evento_html(evento))
        return True, None

    monkeypatch.setattr(rev_mod, "enviar_evento", fake_dispatch)
    return enviadas, monkeypatch, rev_mod


def _patch_http(monkeypatch, rev_mod, html_por_url):
    def handler(request):
        url = str(request.url)
        if url in html_por_url:
            html = html_por_url[url]
            if html is None:
                return httpx.Response(404)
            return httpx.Response(200, html=html)
        return httpx.Response(500)

    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(rev_mod.httpx, "AsyncClient", fake_async_client)


async def test_revalidar_job_remove_encerrada_atualiza_preco_e_notifica(
    store_com_oferta, patched_revalidator
):
    st, oferta = store_com_oferta
    enviadas, mp, rev_mod = patched_revalidator

    html_ativa = (FIX / "promobit_oferta_detail_ativa.html").read_text(encoding="utf-8")
    _patch_http(mp, rev_mod, {"https://promobit.com/oferta/1": html_ativa})

    res = await revalidar_ofertas_ativas(st)
    assert res["checadas"] == 1
    assert res["atualizadas"] == 1
    assert res["removidas"] == 0
    # 600 -> 539.90 = ~10% queda, dispara baixou
    assert res["notif_enviadas"] == 1
    assert any("BAIXOU" in m for m in enviadas)

    atualizada = st.get_oferta_by_id(oferta["id"])
    assert atualizada["preco_atual"] == 539.90
    # 1 inicial (criada) + 1 da revalidacao
    assert len(st.raw()["historico_preco"]) == 2


async def test_revalidar_job_remove_encerrada(store_com_oferta, patched_revalidator):
    st, oferta = store_com_oferta
    _, mp, rev_mod = patched_revalidator
    html_enc = (FIX / "promobit_oferta_detail_encerrada.html").read_text(encoding="utf-8")
    _patch_http(mp, rev_mod, {"https://promobit.com/oferta/1": html_enc})

    res = await revalidar_ofertas_ativas(st)
    assert res["removidas"] == 1
    assert st.get_oferta_by_id(oferta["id"])["ativa"] is False


async def test_revalidar_job_remove_404(store_com_oferta, patched_revalidator):
    st, oferta = store_com_oferta
    _, mp, rev_mod = patched_revalidator
    _patch_http(mp, rev_mod, {"https://promobit.com/oferta/1": None})

    res = await revalidar_ofertas_ativas(st)
    assert res["removidas"] == 1
    assert st.get_oferta_by_id(oferta["id"])["ativa"] is False


async def test_revalidar_job_ignora_inativas(store_com_oferta, patched_revalidator):
    st, oferta = store_com_oferta
    st.update_oferta(oferta["id"], ativa=False)

    _, mp, rev_mod = patched_revalidator
    _patch_http(mp, rev_mod, {})  # sem ofertas ativas, nem chama HTTP

    res = await revalidar_ofertas_ativas(st)
    assert res["checadas"] == 0
