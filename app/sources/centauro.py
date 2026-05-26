"""Source: Centauro (centauro.com.br) — maior varejista esportiva do Brasil.

Usa Playwright para renderizar Next.js e extrair produtos via __NEXT_DATA__.
Foco: tênis de corrida das marcas-alvo com maior desconto.
"""

from app.sources.base_playwright import PlaywrightSource


class CentauroSource(PlaywrightSource):
    nome = "centauro"
    _default_loja = "Centauro"
    _base_url = "https://www.centauro.com.br"

    URLS: dict[str, str] = {
        "tenis-corrida": (
            "https://www.centauro.com.br/tenis/corrida/"
            "?sort=maior-desconto"
        ),
        "asics": (
            "https://www.centauro.com.br/busca/?q=asics+corrida"
            "&sort=maior-desconto"
        ),
        "mizuno": (
            "https://www.centauro.com.br/busca/?q=mizuno+wave"
            "&sort=maior-desconto"
        ),
        "nike-running": (
            "https://www.centauro.com.br/busca/?q=nike+tenis+corrida"
            "&sort=maior-desconto"
        ),
        "adidas-running": (
            "https://www.centauro.com.br/busca/?q=adidas+tenis+corrida"
            "&sort=maior-desconto"
        ),
        "calcados-infantis": (
            "https://www.centauro.com.br/tenis/infantil/"
            "?sort=maior-desconto"
        ),
    }
