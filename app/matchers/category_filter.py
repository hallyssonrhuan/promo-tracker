"""Valida se um titulo de fato pertence a categoria detectada.

Para "corrida", marca sozinha nao basta — Nike/Asics/etc fazem roupas tambem.
Logica:
  - Se titulo cita um MODELO de corrida especifico (ex: "Pegasus"), aceita.
  - Senao, exige a palavra "tenis"/"tênis" + uma keyword generica
    (corrida/running/run). Isso filtra "Calça Asics Run", "Camiseta Nike Running".

Para "maquiagem" e "cabelo", a marca-alvo (Vizzela, Dailus, Lola Cosmetics) ja
basta — sao marcas restritas a esses nichos.

Para "infantil" (sem marca-alvo), expoe `detectar_categoria_por_keyword` que
classifica em "Tenis infantil masc" (34-36) ou "Roupa infantil masc" (10-12).
"""

import re
from typing import Optional

from app.sources.base import normalizar_titulo
from app.sources.brands import (
    KEYWORDS_GENERICAS_CORRIDA, MODELOS_CORRIDA,
    KEYWORDS_PUBLICO_INFANTIL,
    TAMANHOS_TENIS_INFANTIL_MASC,
    TAMANHOS_ROUPA_INFANTIL_MASC,
    TIPOS_ROUPA_INFANTIL,
)


_MODELOS_NORM = [normalizar_titulo(m) for m in MODELOS_CORRIDA]
_KW_GEN_NORM = [normalizar_titulo(k) for k in KEYWORDS_GENERICAS_CORRIDA]

_KW_INFANTIL_NORM = [normalizar_titulo(k) for k in KEYWORDS_PUBLICO_INFANTIL]
_TIPOS_ROUPA_NORM = [normalizar_titulo(t) for t in TIPOS_ROUPA_INFANTIL]

# Regex pra tamanhos de tênis 34/35/36 (palavra inteira)
_RE_TAM_TENIS = re.compile(
    r"\b(" + "|".join(TAMANHOS_TENIS_INFANTIL_MASC) + r")\b"
)

# Regex pra tamanhos de roupa 10/12 anos (varias formas)
_RE_TAM_ROUPA = re.compile(
    "|".join([
        r"\b10\s*anos?\b",
        r"\b12\s*anos?\b",
        r"\b10\s*/\s*12\b",
        r"\b10\s*-\s*12\b",
        r"\btam\.?\s*10\b",
        r"\btam\.?\s*12\b",
        r"\btamanho\s*10\b",
        r"\btamanho\s*12\b",
    ])
)


def validar_categoria(categoria: str, titulo: str) -> bool:
    if categoria == "corrida":
        return _eh_corrida(titulo)
    return True


def _eh_corrida(titulo: str) -> bool:
    norm_padded = " " + normalizar_titulo(titulo) + " "

    for modelo in _MODELOS_NORM:
        if not modelo:
            continue
        if " " in modelo or "-" in modelo:
            if modelo in norm_padded:
                return True
        elif f" {modelo} " in norm_padded:
            return True

    if " tenis " not in norm_padded:
        return False
    return any(f" {kw} " in norm_padded for kw in _KW_GEN_NORM if kw)


# ---------- Categoria sem marca-alvo: infantil masc ----------

def detectar_categoria_por_keyword(titulo: str) -> Optional[tuple[str, str]]:
    """Detecta categoria sem precisar de marca especifica.
    Retorna (marca_label, categoria) ou None.
    """
    norm = normalizar_titulo(titulo)
    if not norm:
        return None
    norm_padded = " " + norm + " "

    if _eh_tenis_infantil_masc(norm, norm_padded):
        return ("Tenis infantil masc", "infantil")
    if _eh_roupa_infantil_masc(norm, norm_padded):
        return ("Roupa infantil masc", "infantil")
    return None


def _eh_publico_infantil_masc(norm_padded: str) -> bool:
    publico = any(f" {kw} " in norm_padded for kw in _KW_INFANTIL_NORM)
    if not publico:
        return False
    # rejeita explicito feminino
    if " menina " in norm_padded or " feminino " in norm_padded or " feminina " in norm_padded:
        return False
    return True


def _eh_tenis_infantil_masc(norm: str, norm_padded: str) -> bool:
    if " tenis " not in norm_padded:
        return False
    if not _eh_publico_infantil_masc(norm_padded):
        return False
    # exige ao menos um tamanho 34/35/36 no titulo
    return bool(_RE_TAM_TENIS.search(norm))


def _eh_roupa_infantil_masc(norm: str, norm_padded: str) -> bool:
    # tipo de roupa
    if not any(f" {t} " in norm_padded for t in _TIPOS_ROUPA_NORM):
        return False
    if not _eh_publico_infantil_masc(norm_padded):
        return False
    return bool(_RE_TAM_ROUPA.search(norm))
