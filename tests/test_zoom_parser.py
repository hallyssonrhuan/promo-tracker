from pathlib import Path

from app.sources.zoom import ZoomSource


FIXTURE = Path(__file__).parent / "fixtures" / "zoom_busca.html"


def test_parse_listagem_extrai_2_ofertas_validas():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = ZoomSource().parse_listagem(html)
    # 4 items: 2 válidos + 1 OutOfStock + 1 sem highPrice
    assert len(ofertas) == 2


def test_parse_listagem_card_nike():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = ZoomSource().parse_listagem(html)
    nike = next(o for o in ofertas if "Nike" in o.titulo)
    assert nike.preco_atual == 399.00
    assert nike.preco_de == 699.00
    assert nike.desconto_pct == 43
    assert nike.fonte == "zoom"
    assert "zoom.com.br" in nike.url
    assert nike.imagem_url and "zoom.com.br" in nike.imagem_url


def test_parse_listagem_card_asics():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = ZoomSource().parse_listagem(html)
    asics = next(o for o in ofertas if "Asics" in o.titulo)
    assert asics.preco_atual == 649.00
    assert asics.preco_de == 999.00
    assert asics.desconto_pct == 35


def test_descarta_out_of_stock():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = ZoomSource().parse_listagem(html)
    titulos = [o.titulo for o in ofertas]
    assert not any("fora de estoque" in t.lower() for t in titulos)


def test_descarta_sem_highprice():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = ZoomSource().parse_listagem(html)
    titulos = [o.titulo for o in ofertas]
    assert not any("sem highPrice" in t for t in titulos)


def test_todos_tem_desconto_real():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = ZoomSource().parse_listagem(html)
    for o in ofertas:
        assert o.preco_de is not None and o.preco_de > o.preco_atual
        assert o.desconto_pct is not None and o.desconto_pct > 0


def test_sem_dados_retorna_vazio():
    ofertas = ZoomSource().parse_listagem("<html><body>sem dados</body></html>")
    assert ofertas == []
