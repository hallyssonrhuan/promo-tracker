"""Testa categoria infantil masc (sem marca-alvo, filtra por keyword + tamanho)."""

from app.matchers.category_filter import detectar_categoria_por_keyword
from app.matchers.pipeline import classificar_e_filtrar
from app.sources.base import OfertaRaw


# ---------- Tênis infantil masc 34/35/36 ----------

def test_tenis_infantil_masc_com_tamanho():
    assert detectar_categoria_por_keyword(
        "Tênis Nike Pico 5 Infantil Masculino do 27 ao 36"
    ) == ("Tenis infantil masc", "infantil")


def test_tenis_infantil_masc_kids():
    assert detectar_categoria_por_keyword(
        "Tenis Adidas Lite Racer Kids 35"
    ) == ("Tenis infantil masc", "infantil")


def test_tenis_infantil_menino_tam_34():
    assert detectar_categoria_por_keyword(
        "Tênis Olympikus Spin Menino 34"
    ) == ("Tenis infantil masc", "infantil")


def test_tenis_infantil_sem_tamanho_alvo_rejeita():
    # tamanho 28 fora do range alvo
    assert detectar_categoria_por_keyword(
        "Tênis Nike infantil tamanho 28"
    ) is None


def test_tenis_infantil_feminino_rejeita():
    assert detectar_categoria_por_keyword(
        "Tênis Adidas infantil menina 35"
    ) is None


def test_adulto_com_tamanho_34_nao_dispara():
    # sem keyword infantil
    assert detectar_categoria_por_keyword(
        "Tênis Nike Air Force 34"
    ) is None


# ---------- Roupa infantil masc 10/12 anos ----------

def test_roupa_camiseta_10_anos():
    assert detectar_categoria_por_keyword(
        "Camiseta Hering Kids Menino 10 anos"
    ) == ("Roupa infantil masc", "infantil")


def test_roupa_conjunto_12_anos():
    assert detectar_categoria_por_keyword(
        "Conjunto infantil masculino tam 12"
    ) == ("Roupa infantil masc", "infantil")


def test_roupa_bermuda_10_12():
    assert detectar_categoria_por_keyword(
        "Bermuda Brandili infantil menino 10/12"
    ) == ("Roupa infantil masc", "infantil")


def test_roupa_sem_tamanho_alvo_rejeita():
    assert detectar_categoria_por_keyword(
        "Camiseta infantil menino 4 anos"
    ) is None


def test_roupa_menina_rejeita():
    assert detectar_categoria_por_keyword(
        "Vestido infantil menina 10 anos"
    ) is None


def test_roupa_sem_tipo_definido_rejeita():
    # "Sapato" nao esta na lista TIPOS_ROUPA
    assert detectar_categoria_por_keyword(
        "Sapato infantil 10 anos"
    ) is None


# ---------- Pipeline integra os 2 caminhos ----------

def test_pipeline_classifica_infantil_e_marca_alvo_juntos():
    brutas = [
        OfertaRaw(titulo="Tenis Asics Gel-Cumulus 26", preco_atual=400, preco_de=800,
                  desconto_pct=50, url="https://x/1", loja="Centauro", fonte="promobit"),
        OfertaRaw(titulo="Tenis Nike Pico 5 infantil masculino 35", preco_atual=150, preco_de=200,
                  desconto_pct=25, url="https://x/2", loja="Centauro", fonte="promobit"),
        OfertaRaw(titulo="Camiseta Brandili menino 10 anos", preco_atual=30, preco_de=60,
                  desconto_pct=50, url="https://x/3", loja="Magalu", fonte="promobit"),
    ]
    out = classificar_e_filtrar(brutas)
    cats = [(c.marca, c.categoria) for c in out]
    assert ("Asics", "corrida") in cats
    assert ("Tenis infantil masc", "infantil") in cats
    assert ("Roupa infantil masc", "infantil") in cats
    assert len(out) == 3
