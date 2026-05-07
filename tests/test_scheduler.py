"""Testa o pipeline coleta com fonte falsa, store em memoria e telegram mockado."""

import pytest

from app.sources.base import OfertaRaw, Source


class FakeSource(Source):
    """Source falsa que devolve uma lista canned. Usada nos testes."""
    nome = "promobit"

    def __init__(self, ofertas: list[OfertaRaw]):
        super().__init__()
        self._ofertas = ofertas

    async def fetch(self) -> list[OfertaRaw]:
        return list(self._ofertas)


@pytest.fixture
def patched_pipeline(store, monkeypatch):
    """Configura SOURCES, mocka enviar_evento e bypassa o verify HTTP."""
    from app import coleta as col_mod

    enviadas: list[str] = []

    async def fake_dispatch(evento):
        from app.notifier.telegram import format_evento_html
        enviadas.append(format_evento_html(evento))
        return True, None

    async def fake_revalidar(client, oferta):
        return {"acao": "manter"}

    monkeypatch.setattr(col_mod, "enviar_evento", fake_dispatch)
    monkeypatch.setattr(col_mod, "revalidar_uma", fake_revalidar)

    def set_source(ofertas):
        monkeypatch.setitem(col_mod.SOURCES, "promobit",
                            lambda: FakeSource(ofertas))

    return set_source, enviadas


def _ofertas_canned():
    return [
        OfertaRaw(
            titulo="Tenis Asics Gel-Cumulus 26", preco_atual=400, preco_de=800,
            desconto_pct=50, url="https://promobit.com/x/1", loja="Centauro",
            fonte="promobit", imagem_url="https://img/1.jpg",
        ),
        OfertaRaw(
            titulo="Base Vizzela Skin Tint", preco_atual=64.90, preco_de=89.90,
            desconto_pct=28, url="https://promobit.com/x/2", loja="Amazon",
            fonte="promobit", imagem_url="https://img/2.jpg",
        ),
        # Marca nao-alvo: tem que ser ignorada
        OfertaRaw(
            titulo="Smartphone Samsung Galaxy", preco_atual=2000, preco_de=3000,
            desconto_pct=33, url="https://promobit.com/x/3", loja="Magalu",
            fonte="promobit",
        ),
    ]


@pytest.mark.asyncio
async def test_executar_coleta_pipeline_completo(store, patched_pipeline):
    set_source, enviadas = patched_pipeline
    set_source(_ofertas_canned())

    from app.coleta import executar_coleta
    resumo = await executar_coleta(store, "promobit")

    info = resumo["promobit"]
    assert info["sucesso"] is True
    assert info["brutas"] == 3
    assert info["classificadas"] == 2  # Samsung filtrada
    assert info["eventos"] == 2        # ambas com desconto >= 20%
    assert info["enviados"] == 2

    # Telegram recebeu 2 mensagens
    assert len(enviadas) == 2
    joined = "\n".join(enviadas)
    assert "Asics" in joined
    assert "Vizzela" in joined

    # Persistencia: 2 produtos, 2 ofertas, 2 historico, 2 notificacoes
    raw = store.raw()
    assert len(raw["produtos"]) == 2
    assert len(raw["ofertas"]) == 2
    assert len(raw["historico_preco"]) == 2
    assert len(raw["notificacoes"]) == 2
    assert all(n["sucesso"] for n in raw["notificacoes"])


@pytest.mark.asyncio
async def test_executar_coleta_marca_status_ok(store, patched_pipeline):
    set_source, _ = patched_pipeline
    set_source(_ofertas_canned())

    from app.coleta import executar_coleta
    await executar_coleta(store, "promobit")

    fonte = store.get_fonte("promobit")
    assert fonte["ultima_coleta_status"] == "ok"
    assert fonte["ultima_coleta_em"] is not None
    assert fonte["ultima_coleta_qtd"] == 2


@pytest.mark.asyncio
async def test_executar_coleta_source_que_falha_marca_erro(store, monkeypatch):
    from app import coleta as col_mod

    class SourceQuebrada(Source):
        nome = "promobit"
        async def fetch(self):
            raise RuntimeError("seletor mudou")

    monkeypatch.setitem(col_mod.SOURCES, "promobit", lambda: SourceQuebrada())

    resumo = await col_mod.executar_coleta(store, "promobit")
    assert resumo["promobit"]["sucesso"] is False
    assert "seletor" in resumo["promobit"]["erro"]

    fonte = store.get_fonte("promobit")
    assert fonte["ultima_coleta_status"] == "erro"
    assert "seletor" in fonte["ultima_coleta_erro"]


@pytest.mark.asyncio
async def test_executar_coleta_segunda_rodada_detecta_queda(store, patched_pipeline):
    set_source, enviadas = patched_pipeline

    # 1a coleta: preço 400
    set_source([OfertaRaw(
        titulo="Tenis Asics Gel-Cumulus 26", preco_atual=400, preco_de=800,
        desconto_pct=50, url="https://promobit.com/x/1", loja="Centauro",
        fonte="promobit",
    )])
    from app.coleta import executar_coleta
    await executar_coleta(store, "promobit")
    assert len(enviadas) == 1  # nova oferta

    # 2a coleta: caiu pra 300 (queda de 25%)
    set_source([OfertaRaw(
        titulo="Tenis Asics Gel-Cumulus 26", preco_atual=300, preco_de=800,
        desconto_pct=63, url="https://promobit.com/x/1", loja="Centauro",
        fonte="promobit",
    )])
    await executar_coleta(store, "promobit")

    # Nao deve duplicar nova (mesma oferta), mas deve disparar "baixou"
    assert len(enviadas) == 2
    assert "BAIXOU" in enviadas[1]
