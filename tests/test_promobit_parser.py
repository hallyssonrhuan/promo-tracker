from pathlib import Path

from app.sources.base import OfertaRaw, normalizar_titulo, parse_preco_br
from app.sources.promobit import PromobitSource


FIXTURE = Path(__file__).parent / "fixtures" / "promobit_listagem.html"


def test_parse_listagem_extrai_5_ofertas_validas():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PromobitSource().parse_listagem(html)
    # 7 cards: 5 validos + 1 encerrado (OutOfStock) + 1 sem preco_de (sem desconto)
    assert len(ofertas) == 5
    titulos = [o.titulo for o in ofertas]
    assert "Produto encerrado — deve ser descartado" not in titulos
    assert all("sem desconto real" not in t for t in titulos)


def test_parse_listagem_card_completo():
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PromobitSource().parse_listagem(html)
    asics = ofertas[0]
    assert "Asics" in asics.titulo
    assert asics.preco_atual == 539.90
    assert asics.preco_de == 899.90
    assert asics.desconto_pct == 40
    assert asics.loja == "Centauro"
    assert asics.fonte == "promobit"
    assert asics.imagem_url and asics.imagem_url.startswith("https://")
    assert asics.url.startswith("https://www.promobit.com.br/")


def test_filtra_availability_e_sem_desconto():
    """Cards sem availability InStock/LimitedAvailability ou sem preco_de
    devem ser descartados (politica: so persistir promocoes reais)."""
    html = FIXTURE.read_text(encoding="utf-8")
    ofertas = PromobitSource().parse_listagem(html)
    # Todos devem ter desconto > 0 e preco_de definido
    for o in ofertas:
        assert o.preco_de is not None
        assert o.preco_de > o.preco_atual
        assert o.desconto_pct and o.desconto_pct > 0


def test_parse_preco_br():
    assert parse_preco_br("R$ 1.299,90") == 1299.90
    assert parse_preco_br("R$ 99,00") == 99.00
    assert parse_preco_br("539,90") == 539.90
    assert parse_preco_br("1299") == 1299.0
    assert parse_preco_br("") is None
    assert parse_preco_br("texto") is None


def test_hash_unico_dedup_por_url_loja_fonte():
    o1 = OfertaRaw(titulo="X", preco_atual=10, url="https://a.com/1", loja="L", fonte="promobit")
    o2 = OfertaRaw(titulo="Y", preco_atual=20, url="https://a.com/1", loja="L", fonte="promobit")
    o3 = OfertaRaw(titulo="X", preco_atual=10, url="https://a.com/2", loja="L", fonte="promobit")
    o4 = OfertaRaw(titulo="X", preco_atual=10, url="https://a.com/1", loja="L", fonte="pelando")
    assert o1.hash_unico == o2.hash_unico
    assert o1.hash_unico != o3.hash_unico
    assert o1.hash_unico != o4.hash_unico


def test_normalizar_titulo():
    assert normalizar_titulo("Tenis Asics  Gel-Cumulus") == "tenis asics gel-cumulus"
    assert normalizar_titulo("MULTIPLOS    espacos") == "multiplos espacos"
    # Pontuação (`,`, `:`, `.`, etc.) é removida pra evitar diferenças idiotas
    # tipo "Lola, Cosmetics" vs "Lola , Cosmetics" virarem produtos distintos.
    assert normalizar_titulo("Acentuacao: ção, ã, é") == "acentuacao cao a e"
    assert normalizar_titulo("Lola Rapunzel, 250ml") == normalizar_titulo("Lola Rapunzel , 250ml")
    assert normalizar_titulo("") == ""
    assert normalizar_titulo(None) == ""
