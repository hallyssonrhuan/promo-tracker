from pathlib import Path

from app.sources.pelando import PelandoSource


FIXTURE = Path(__file__).parent / "fixtures" / "pelando_listagem.html"


def test_parse_listagem_extrai_3_ofertas_validas():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PelandoSource().parse_listagem(html)
    # 5 cards: 3 válidos + 1 sem originalPrice + 1 preco_de < preco_atual
    assert len(ofertas) == 3


def test_parse_listagem_card_asics():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PelandoSource().parse_listagem(html)
    asics = next(o for o in ofertas if "Asics" in o.titulo)
    assert asics.preco_atual == 499.90
    assert asics.preco_de == 799.90
    assert asics.desconto_pct == 38
    assert asics.loja == "Netshoes"
    assert asics.fonte == "pelando"
    assert asics.url == "https://www.pelando.com.br/oferta/100/tenis-asics-gel-cumulus"
    assert asics.imagem_url and "pelando" in asics.imagem_url


def test_parse_listagem_card_vizzela():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PelandoSource().parse_listagem(html)
    vizzela = next(o for o in ofertas if "Vizzela" in o.titulo)
    assert vizzela.preco_atual == 29.90
    assert vizzela.preco_de == 59.90
    assert vizzela.loja == "Amazon"
    assert vizzela.fonte == "pelando"


def test_descarta_sem_preco_de():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PelandoSource().parse_listagem(html)
    titulos = [o.titulo for o in ofertas]
    assert not any("sem originalPrice" in t for t in titulos)
    assert not any("preco_de menor" in t for t in titulos)


def test_todos_tem_desconto_real():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PelandoSource().parse_listagem(html)
    for o in ofertas:
        assert o.preco_de is not None and o.preco_de > o.preco_atual
        assert o.desconto_pct is not None and o.desconto_pct > 0


def test_fallback_jsonld_sem_next_data():
    """Se não houver __NEXT_DATA__, o parser não deve quebrar (retorna [])."""
    ofertas = PelandoSource().parse_listagem("<html><body>sem dados</body></html>")
    assert ofertas == []
