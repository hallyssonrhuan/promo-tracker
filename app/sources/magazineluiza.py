"""Source: Magazine Luiza (magazineluiza.com.br).

Usa Playwright + page.evaluate() para extrair __NEXT_DATA__ do Next.js SSR.
Cobre todas as categorias rastreadas: tênis corrida, maquiagem, cabelo, infantil.
"""

from app.sources.base_playwright import PlaywrightSource


class MagazineLuizaSource(PlaywrightSource):
    nome = "magazineluiza"
    _default_loja = "Magazine Luiza"
    _base_url = "https://www.magazineluiza.com.br"

    URLS: dict[str, str] = {
        # Tênis corrida por marca
        "asics": "https://www.magazineluiza.com.br/busca/asics+tenis+corrida/",
        "mizuno": "https://www.magazineluiza.com.br/busca/mizuno+wave/",
        "nike-corrida": "https://www.magazineluiza.com.br/busca/nike+tenis+corrida/",
        "adidas-corrida": "https://www.magazineluiza.com.br/busca/adidas+tenis+corrida/",
        # Maquiagem
        "vizzela": "https://www.magazineluiza.com.br/busca/vizzela/",
        "dailus": "https://www.magazineluiza.com.br/busca/dailus/",
        # Cabelo
        "lola-cosmetics": "https://www.magazineluiza.com.br/busca/lola+cosmetics/",
        # Infantil
        "tenis-infantil": "https://www.magazineluiza.com.br/busca/tenis+infantil+menino/",
    }
