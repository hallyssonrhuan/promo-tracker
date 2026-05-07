"""Marcas-alvo e palavras-chave de classificação.

Editar este arquivo é a forma mais comum de manutenção: adicionar variação
de escrita, nova linha de produto, ou novo modelo de tênis.
"""

# Cada marca: nome canônico -> lista de variações (em lowercase, sem acento)
MARCAS_TENIS_CORRIDA: dict[str, list[str]] = {
    "Asics": ["asics"],
    "Mizuno": ["mizuno"],
    "Nike": ["nike"],
    "Adidas": ["adidas"],
    "Olympikus": ["olympikus"],
    "Fila": ["fila"],
    "Brooks": ["brooks"],
    "Saucony": ["saucony"],
}

# Modelos especificos de tênis de corrida — match por modelo SOZINHO basta
MODELOS_CORRIDA: list[str] = [
    # Asics
    "gt-2000", "gel-nimbus", "gel-cumulus", "gel-kayano", "gel-pulse",
    "gel-excite", "gel-contend", "novablast",
    # Mizuno
    "wave rider", "wave inspire", "wave sky", "wave prophecy", "wave creation",
    # Nike
    "pegasus", "vomero", "structure", "react infinity", "zoom fly",
    "alphafly", "vaporfly",
    # Adidas
    "adizero", "ultraboost", "supernova", "solar boost", "solarglide",
    # Brooks
    "ghost", "glycerin", "launch", "adrenaline gts", "hyperion",
    # Saucony
    "endorphin", "kinvara", "triumph",
    # Olympikus
    "corre 2", "corre 3",
]

# Palavras genericas — sozinhas nao bastam (Asics Run pode ser roupa).
# So validam corrida em conjunto com a palavra "tenis".
KEYWORDS_GENERICAS_CORRIDA: list[str] = [
    "corrida", "running", "runner", "run",
]

MARCAS_MAQUIAGEM: dict[str, list[str]] = {
    "Vizzela": ["vizzela", "vizela", "vizzella"],
    "Dailus": ["dailus"],
}

# "Lola" sozinho e ambíguo (cantora, marca de roupa, etc.)
# Exigir "lola cosmetics" OU nome de linha conhecida.
MARCAS_CABELO: dict[str, list[str]] = {
    "Lola Cosmetics": ["lola cosmetics", "lolacosmetics"],
}

# ---------- INFANTIL MASCULINO ----------
# Diferente das marcas-alvo acima, aqui aceita QUALQUER marca — filtra por
# publico (infantil/menino) + tamanho.

KEYWORDS_PUBLICO_INFANTIL: list[str] = [
    "infantil", "kids", "menino", "juvenil", "boy", "garoto",
]

# Tamanhos aceitos pra TENIS infantil masc
TAMANHOS_TENIS_INFANTIL_MASC: list[str] = ["34", "35", "36"]

# Tamanhos aceitos pra ROUPA infantil masc (10-12 anos)
TAMANHOS_ROUPA_INFANTIL_MASC: list[str] = [
    "10 anos", "12 anos", "10/12", "10-12",
    "tam 10", "tam 12", "tamanho 10", "tamanho 12",
]

# Tipos de roupa que nos interessam (filtra acessorios fora)
TIPOS_ROUPA_INFANTIL: list[str] = [
    "camiseta", "camisa", "bermuda", "short", "calca",
    "conjunto", "pijama", "agasalho", "blusa", "moletom",
    "regata", "polo", "jaqueta", "casaco", "macacao", "jeans",
]


LINHAS_LOLA: list[str] = [
    "meu cacho minha vida",
    "morte subita",
    "santo poderoso creeposo",
    "creeposo",
    "be(m)dita ghee",
    "bemdita ghee",
    "rapunzel",
    "lavou. ta pronto",
    "lavou ta pronto",
    "no problemo",
    "queratina vegetal",
    "the brushone",
    "twister",
]


def todas_variacoes_marca() -> dict[str, tuple[str, str]]:
    """Retorna {variacao_lowercase: (marca_canonica, categoria)} pra lookup."""
    out: dict[str, tuple[str, str]] = {}
    for marca, variacoes in MARCAS_TENIS_CORRIDA.items():
        for v in variacoes:
            out[v] = (marca, "corrida")
    for marca, variacoes in MARCAS_MAQUIAGEM.items():
        for v in variacoes:
            out[v] = (marca, "maquiagem")
    for marca, variacoes in MARCAS_CABELO.items():
        for v in variacoes:
            out[v] = (marca, "cabelo")
    for linha in LINHAS_LOLA:
        out[linha] = ("Lola Cosmetics", "cabelo")
    return out
