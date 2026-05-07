"""Detecta marca-alvo no titulo da oferta."""

import re
from typing import Optional

from app.sources.base import normalizar_titulo
from app.sources.brands import todas_variacoes_marca


_VARIACOES_CACHE: Optional[dict[str, tuple[str, str]]] = None


def _variacoes() -> dict[str, tuple[str, str]]:
    global _VARIACOES_CACHE
    if _VARIACOES_CACHE is None:
        # ordenar por tamanho decrescente: variacao mais especifica casa primeiro
        _VARIACOES_CACHE = dict(
            sorted(todas_variacoes_marca().items(), key=lambda kv: -len(kv[0]))
        )
    return _VARIACOES_CACHE


def _contem(texto: str, padrao: str) -> bool:
    if " " in padrao:
        return padrao in texto
    return re.search(rf"\b{re.escape(padrao)}\b", texto) is not None


def detectar_marca(titulo: str) -> Optional[tuple[str, str]]:
    """Retorna (marca_canonica, categoria) se titulo menciona marca-alvo, senao None."""
    norm = normalizar_titulo(titulo)
    if not norm:
        return None
    for variacao, (marca, categoria) in _variacoes().items():
        if _contem(norm, variacao):
            return (marca, categoria)
    return None
