"""Source: Americanas (americanas.com.br).

Usa Playwright para renderizar Next.js + GraphQL e extrair produtos.
A Americanas usa Apollo GraphQL — dados disponíveis via __NEXT_DATA__ ou
Apollo state após renderização.
"""

from app.sources.base_playwright import PlaywrightSource


class AmericanasSource(PlaywrightSource):
    nome = "americanas"
    _default_loja = "Americanas"
    _base_url = "https://www.americanas.com.br"

    URLS: dict[str, str] = {
        # Tênis corrida
        "asics": "https://www.americanas.com.br/busca/asics%20tenis%20corrida",
        "mizuno": "https://www.americanas.com.br/busca/mizuno%20wave",
        "nike-corrida": "https://www.americanas.com.br/busca/nike%20tenis%20corrida",
        "adidas-corrida": "https://www.americanas.com.br/busca/adidas%20ultraboost",
        # Maquiagem
        "vizzela": "https://www.americanas.com.br/busca/vizzela",
        "dailus": "https://www.americanas.com.br/busca/dailus",
        # Cabelo
        "lola-cosmetics": "https://www.americanas.com.br/busca/lola%20cosmetics",
        # Infantil
        "tenis-infantil": "https://www.americanas.com.br/busca/tenis%20infantil%20menino",
    }
