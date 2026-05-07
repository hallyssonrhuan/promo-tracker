from app.matchers.pipeline import OfertaClassificada
from app.notifier.rules import gerar_eventos, registrar_envio
from app.notifier.telegram import format_evento_html
from app.sources.base import OfertaRaw


def _oc(titulo, preco_atual, preco_de=None, desconto_pct=None,
        url="https://promobit.com/x/1", loja="Centauro",
        marca="Asics", categoria="corrida"):
    return OfertaClassificada(
        oferta=OfertaRaw(
            titulo=titulo,
            preco_atual=preco_atual,
            preco_de=preco_de,
            desconto_pct=desconto_pct,
            url=url,
            loja=loja,
            fonte="promobit",
        ),
        marca=marca,
        categoria=categoria,
    )


def test_nova_oferta_acima_do_minimo_gera_evento_nova(store):
    oc = _oc("Tenis Asics Gel-Cumulus 26", 400, 800, 50)
    eventos = gerar_eventos([oc], store)
    assert len(eventos) == 1
    assert eventos[0].tipo == "nova"
    # persistiu produto + oferta + historico
    assert len(store.raw()["produtos"]) == 1
    assert len(store.raw()["ofertas"]) == 1
    assert len(store.raw()["historico_preco"]) == 1


def test_nova_oferta_abaixo_do_minimo_nao_gera_evento(store):
    oc = _oc("Tenis Asics Gel-Cumulus 26", 720, 800, 10)  # 10% < 20% min
    eventos = gerar_eventos([oc], store)
    assert eventos == []
    # mas persistiu mesmo assim
    assert len(store.raw()["ofertas"]) == 1


def test_oferta_existente_com_queda_gera_evento_baixou(store):
    oc1 = _oc("Tenis Asics Gel-Cumulus 26", 600, 800, 25)
    gerar_eventos([oc1], store)

    oc2 = _oc("Tenis Asics Gel-Cumulus 26", 500, 800, 38)  # caiu de 600 pra 500 (~16%)
    eventos = gerar_eventos([oc2], store)
    assert len(eventos) == 1
    assert eventos[0].tipo == "baixou"
    assert eventos[0].preco_anterior == 600

    # 2 entradas no historico
    assert len(store.raw()["historico_preco"]) == 2


def test_oferta_existente_sem_queda_relevante_nao_gera_evento(store):
    oc1 = _oc("Tenis Asics Gel-Cumulus 26", 600, 800, 25)
    gerar_eventos([oc1], store)

    oc2 = _oc("Tenis Asics Gel-Cumulus 26", 595, 800, 26)  # caiu <1%
    eventos = gerar_eventos([oc2], store)
    assert eventos == []


def test_nao_renotifica_mesma_oferta_em_24h(store):
    oc = _oc("Tenis Asics Gel-Cumulus 26", 400, 800, 50)
    eventos1 = gerar_eventos([oc], store)
    assert len(eventos1) == 1
    registrar_envio(store, eventos1[0], sucesso=True, erro=None)

    # rodar de novo: nao deve emitir
    eventos2 = gerar_eventos([oc], store)
    assert eventos2 == []


def test_cap_max_notificacoes_por_job(store, monkeypatch):
    from app.notifier import rules as rules_mod
    monkeypatch.setattr(rules_mod.settings, "max_notificacoes_por_job", 3)

    classificadas = [
        _oc(f"Tenis Asics modelo {i}", 100, 200, 50, url=f"https://promobit.com/x/{i}")
        for i in range(10)
    ]
    eventos = gerar_eventos(classificadas, store)
    assert len(eventos) == 3


def test_ordena_por_maior_desconto(store):
    classificadas = [
        _oc("Tenis Asics A", 80, 100, 20, url="https://promobit.com/a"),
        _oc("Tenis Asics B", 30, 100, 70, url="https://promobit.com/b"),
        _oc("Tenis Asics C", 50, 100, 50, url="https://promobit.com/c"),
    ]
    eventos = gerar_eventos(classificadas, store)
    assert [e.classificada.oferta.titulo for e in eventos] == [
        "Tenis Asics B", "Tenis Asics C", "Tenis Asics A",
    ]


# ---------- format_evento_html ----------

def test_format_evento_html_nova_com_desconto(store):
    oc = _oc("Tenis Asics Gel-Cumulus 26", 400, 800, 50)
    eventos = gerar_eventos([oc], store)
    msg = format_evento_html(eventos[0])
    assert "NOVA OFERTA" in msg
    assert "Asics" in msg
    assert "Centauro" in msg
    assert "R$ 400,00" in msg
    assert "R$ 800,00" in msg
    assert "-50%" in msg or "50%" in msg
    assert "<a href=" in msg
    assert "🔥" in msg


def test_format_evento_html_escapa_html_no_titulo(store):
    oc = _oc('Tenis <script>alert(1)</script>', 400, 800, 50,
             url="https://promobit.com/xss")
    eventos = gerar_eventos([oc], store)
    msg = format_evento_html(eventos[0])
    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg


def test_format_evento_html_baixou_inclui_preco_anterior(store):
    oc1 = _oc("Tenis Asics", 600, 800, 25)
    gerar_eventos([oc1], store)
    oc2 = _oc("Tenis Asics", 500, 800, 38)
    eventos = gerar_eventos([oc2], store)
    msg = format_evento_html(eventos[0])
    assert "BAIXOU" in msg
    assert "Caiu de" in msg
    assert "R$ 600,00" in msg
