"""Dedupe de ofertas por hash_unico (fonte+loja+url)."""

from app.sources.base import OfertaRaw


def dedupe(ofertas: list[OfertaRaw]) -> list[OfertaRaw]:
    """Em caso de duplicata mesmo hash, mantem a de menor preco_atual."""
    by_hash: dict[str, OfertaRaw] = {}
    for o in ofertas:
        atual = by_hash.get(o.hash_unico)
        if atual is None or o.preco_atual < atual.preco_atual:
            by_hash[o.hash_unico] = o
    return list(by_hash.values())
