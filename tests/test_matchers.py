from app.sources.base import OfertaRaw
from app.matchers.brand_filter import detectar_marca
from app.matchers.category_filter import validar_categoria
from app.matchers.deduper import dedupe
from app.matchers.pipeline import classificar_e_filtrar


# ---------- brand_filter ----------

def test_detecta_asics():
    assert detectar_marca("Tenis Asics Gel-Cumulus 26") == ("Asics", "corrida")


def test_detecta_vizzela_com_variacoes():
    assert detectar_marca("Base Vizzela Skin Tint") == ("Vizzela", "maquiagem")
    assert detectar_marca("Base VIZELA matte") == ("Vizzela", "maquiagem")
    assert detectar_marca("Vizzella sombras") == ("Vizzela", "maquiagem")


def test_detecta_dailus():
    assert detectar_marca("Batom Dailus Liquido") == ("Dailus", "maquiagem")


def test_detecta_lola_cosmetics_explicito():
    assert detectar_marca("Kit Lola Cosmetics Hidratacao") == ("Lola Cosmetics", "cabelo")


def test_detecta_lola_via_linha_conhecida():
    assert detectar_marca("Mascara Meu Cacho Minha Vida 230g") == ("Lola Cosmetics", "cabelo")
    assert detectar_marca("Creeposo Leave-in 250ml") == ("Lola Cosmetics", "cabelo")


def test_lola_sozinho_nao_dispara():
    # "lola" sozinho e ambiguo (cantora, marca de roupa)
    assert detectar_marca("Camiseta Lola Tamanho M") is None


def test_marca_nao_alvo_retorna_none():
    assert detectar_marca("Tenis Olympikus modelo X") == ("Olympikus", "corrida")
    assert detectar_marca("Smartphone Samsung Galaxy") is None
    assert detectar_marca("Shampoo Pantene") is None


def test_word_boundary_evita_substring_falsa():
    # "nike" nao deve casar em "biking" (palavra diferente)
    assert detectar_marca("Equipamento de biking") is None


def test_titulo_vazio():
    assert detectar_marca("") is None
    assert detectar_marca(None) is None


# ---------- category_filter ----------

def test_corrida_exige_keyword():
    # Nike sem keyword de corrida → recusa
    assert validar_categoria("corrida", "Tenis Nike Air Force") is False
    # Nike com modelo de corrida → aceita
    assert validar_categoria("corrida", "Tenis Nike Pegasus 41") is True
    # Asics com palavra "corrida" + tenis
    assert validar_categoria("corrida", "Tenis Asics para corrida") is True
    # Asics com modelo
    assert validar_categoria("corrida", "Tenis Asics Gel-Cumulus 26") is True


def test_corrida_rejeita_roupa_esportiva():
    # Esses sao casos REAIS de marcas de corrida vendendo roupa.
    assert validar_categoria("corrida", "Calça Legging Asics Run Cós Baixo") is False
    assert validar_categoria("corrida", "Camiseta Nike Running Masculina") is False
    assert validar_categoria("corrida", "Mochila Asics Endurance") is False
    # Mas tenis com modelo passa
    assert validar_categoria("corrida", "Tenis Asics Novablast 4") is True
    # Tenis + run também (tem "tenis")
    assert validar_categoria("corrida", "Tenis Nike Run Defy Feminino") is True


def test_maquiagem_e_cabelo_aceitam_so_pela_marca():
    assert validar_categoria("maquiagem", "Qualquer titulo") is True
    assert validar_categoria("cabelo", "Qualquer titulo") is True


# ---------- deduper ----------

def test_dedupe_mantem_menor_preco():
    o1 = OfertaRaw(titulo="X", preco_atual=100, url="https://a.com/1", loja="L", fonte="promobit")
    o2 = OfertaRaw(titulo="X", preco_atual=80, url="https://a.com/1", loja="L", fonte="promobit")
    o3 = OfertaRaw(titulo="X", preco_atual=120, url="https://a.com/1", loja="L", fonte="promobit")
    out = dedupe([o1, o2, o3])
    assert len(out) == 1
    assert out[0].preco_atual == 80


def test_dedupe_preserva_distintos():
    o1 = OfertaRaw(titulo="X", preco_atual=100, url="https://a.com/1", loja="L1", fonte="promobit")
    o2 = OfertaRaw(titulo="X", preco_atual=100, url="https://a.com/2", loja="L1", fonte="promobit")
    o3 = OfertaRaw(titulo="X", preco_atual=100, url="https://a.com/1", loja="L2", fonte="promobit")
    out = dedupe([o1, o2, o3])
    assert len(out) == 3


# ---------- pipeline ----------

def test_pipeline_filtra_marca_alvo_e_classifica():
    brutas = [
        OfertaRaw(titulo="Tenis Asics Gel-Cumulus 26", preco_atual=539.90,
                  url="https://a.com/1", loja="Centauro", fonte="promobit"),
        OfertaRaw(titulo="Tenis Nike Air Force lifestyle", preco_atual=499,
                  url="https://a.com/2", loja="Nike", fonte="promobit"),
        OfertaRaw(titulo="Base Vizzela Skin Tint", preco_atual=64.90,
                  url="https://a.com/3", loja="Amazon", fonte="promobit"),
        OfertaRaw(titulo="Smartphone Samsung Galaxy", preco_atual=2000,
                  url="https://a.com/4", loja="Magalu", fonte="promobit"),
        OfertaRaw(titulo="Mascara Meu Cacho Minha Vida", preco_atual=89.90,
                  url="https://a.com/5", loja="Beleza na Web", fonte="promobit"),
    ]
    classificadas = classificar_e_filtrar(brutas)
    titulos = [(c.marca, c.categoria) for c in classificadas]
    assert ("Asics", "corrida") in titulos
    assert ("Vizzela", "maquiagem") in titulos
    assert ("Lola Cosmetics", "cabelo") in titulos
    # Nike Air Force rejeitada (sem keyword de corrida); Samsung rejeitada (marca nao-alvo)
    assert len(classificadas) == 3


def test_pipeline_dedupe_antes_de_classificar():
    o = OfertaRaw(titulo="Tenis Asics Gel-Cumulus 26", preco_atual=539.90,
                  url="https://a.com/1", loja="Centauro", fonte="promobit")
    o_dup = OfertaRaw(titulo="Tenis Asics Gel-Cumulus 26", preco_atual=499,
                      url="https://a.com/1", loja="Centauro", fonte="promobit")
    out = classificar_e_filtrar([o, o_dup])
    assert len(out) == 1
    assert out[0].oferta.preco_atual == 499  # menor preco
