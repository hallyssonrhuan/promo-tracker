"""Source: Netshoes (netshoes.com.br) — loja especializada em esportes/tênis.

Usa Playwright para renderizar o React SPA e extrair produtos via JS state.
Foco: tênis de corrida e calçados infantis com maior desconto.
"""

from app.sources.base_playwright import PlaywrightSource


class NetshoesSource(PlaywrightSource):
    nome = "netshoes"
    _default_loja = "Netshoes"
    _base_url = "https://www.netshoes.com.br"

    URLS: dict[str, str] = {
        "corrida-masc": (
            "https://www.netshoes.com.br/tenis-corrida-masculino"
            "?pagina=1&ordenacao=maior-desconto"
        ),
        "corrida-fem": (
            "https://www.netshoes.com.br/tenis-corrida-feminino"
            "?pagina=1&ordenacao=maior-desconto"
        ),
        "asics": (
            "https://www.netshoes.com.br/marcas/asics"
            "?pagina=1&ordenacao=maior-desconto"
        ),
        "mizuno": (
            "https://www.netshoes.com.br/marcas/mizuno"
            "?pagina=1&ordenacao=maior-desconto"
        ),
        "brooks": (
            "https://www.netshoes.com.br/marcas/brooks"
            "?pagina=1&ordenacao=maior-desconto"
        ),
        "calcados-infantis": (
            "https://www.netshoes.com.br/calcados-infantis"
            "?pagina=1&ordenacao=maior-desconto"
        ),
    }
