"""Testa dedupe (produto+loja) no Store — desativa duplicatas."""

from app.matchers.pipeline import OfertaClassificada
from app.notifier.rules import gerar_eventos
from app.sources.base import OfertaRaw


def _oc(titulo, preco, url, loja="Amazon"):
    return OfertaClassificada(
        oferta=OfertaRaw(
            titulo=titulo, preco_atual=preco, preco_de=preco * 2,
            desconto_pct=50, url=url, loja=loja, fonte="promobit",
        ),
        marca="Lola Cosmetics", categoria="cabelo",
    )


def _ofertas_ativas(store):
    return [o for o in store.raw()["ofertas"].values() if o.get("ativa")]


def test_dedupe_desativa_a_mais_cara(store):
    # 2 ofertas pro mesmo produto Lola, mesma loja, URLs diferentes (Promobit
    # cria entradas separadas), preços diferentes
    gerar_eventos([_oc("Lola Rapunzel Milk Leave-in", 89.90,
                       "https://promobit.com/oferta/lola-rapunzel-A")], store)
    gerar_eventos([_oc("Lola Rapunzel Milk Leave-in", 79.90,
                       "https://promobit.com/oferta/lola-rapunzel-B")], store)

    ativas = _ofertas_ativas(store)
    assert len(ativas) == 1
    assert ativas[0]["preco_atual"] == 79.90  # a mais barata sobreviveu


def test_dedupe_diferentes_lojas_nao_conflita(store):
    gerar_eventos([_oc("Lola Rapunzel", 89.90, "https://promobit/A", loja="Amazon")], store)
    gerar_eventos([_oc("Lola Rapunzel", 79.90, "https://promobit/B", loja="Magalu")], store)
    ativas = _ofertas_ativas(store)
    assert len(ativas) == 2  # cada loja mantem a sua


def test_dedupe_helper_aplicado_em_base_existente(store):
    gerar_eventos([_oc("Lola X", 100, "https://promobit/1")], store)
    gerar_eventos([_oc("Lola X", 80, "https://promobit/2")], store)
    gerar_eventos([_oc("Lola X", 90, "https://promobit/3")], store)

    # Apos as 3 chamadas, dedupe automatico ja deixou so a mais barata (80)
    ativas = _ofertas_ativas(store)
    assert len(ativas) == 1
    assert ativas[0]["preco_atual"] == 80
