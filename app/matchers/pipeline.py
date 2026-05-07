"""Pipeline: brutas → marca detectada → categoria validada → dedupe."""

from dataclasses import dataclass

from app.sources.base import OfertaRaw
from app.matchers.brand_filter import detectar_marca
from app.matchers.category_filter import detectar_categoria_por_keyword, validar_categoria
from app.matchers.deduper import dedupe


@dataclass
class OfertaClassificada:
    oferta: OfertaRaw
    marca: str
    categoria: str


def classificar_e_filtrar(brutas: list[OfertaRaw]) -> list[OfertaClassificada]:
    deduplicadas = dedupe(brutas)
    out: list[OfertaClassificada] = []
    for o in deduplicadas:
        # 1) Tenta marca-alvo (Asics, Vizzela, Lola, etc.)
        detectado = detectar_marca(o.titulo)
        if detectado:
            marca, categoria = detectado
            if validar_categoria(categoria, o.titulo):
                out.append(OfertaClassificada(oferta=o, marca=marca, categoria=categoria))
                continue
            # marca detectada mas categoria invalida — cai no fallback infantil
            # (ex: "Tenis Nike infantil 35" — Nike sem keyword corrida, mas
            # eh tenis infantil valido)

        # 2) Categoria por keyword (infantil masc — sem marca alvo)
        cat_kw = detectar_categoria_por_keyword(o.titulo)
        if cat_kw:
            marca_label, categoria = cat_kw
            out.append(OfertaClassificada(oferta=o, marca=marca_label, categoria=categoria))
    return out
