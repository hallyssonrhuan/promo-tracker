"""Source: Amazon Brasil (amazon.com.br).

Usa Playwright com filtro de desconto na URL (&rh=p_n_pct-off-with-tax%3A25-100).
Amazon exige renderização JS completa e headers de navegador reais.

A Amazon embute JSON-LD nas páginas de busca quando o resultado é um produto;
o fallback heurístico no JS state cobre os demais casos.
"""

from app.sources.base_playwright import PlaywrightSource


class AmazonSource(PlaywrightSource):
    nome = "amazon"
    _default_loja = "Amazon"
    _base_url = "https://www.amazon.com.br"
    # Aguarda os cards de produto antes de parsear
    _wait_selector = "[data-component-type='s-search-result']"
    _idle_timeout = 12_000

    # Filtro de 25%+ de desconto embutido na URL (&rh=...25-100)
    _DISCOUNT_FILTER = "&rh=p_n_pct-off-with-tax%3A25-100"

    URLS: dict[str, str] = {
        # Tênis corrida
        "asics-corrida": (
            "https://www.amazon.com.br/s?k=asics+tenis+corrida"
            + _DISCOUNT_FILTER
        ),
        "mizuno-corrida": (
            "https://www.amazon.com.br/s?k=mizuno+wave+tenis"
            + _DISCOUNT_FILTER
        ),
        "nike-corrida": (
            "https://www.amazon.com.br/s?k=nike+tenis+corrida"
            + _DISCOUNT_FILTER
        ),
        "brooks": (
            "https://www.amazon.com.br/s?k=brooks+tenis+corrida"
            + _DISCOUNT_FILTER
        ),
        "saucony": (
            "https://www.amazon.com.br/s?k=saucony+tenis"
            + _DISCOUNT_FILTER
        ),
        # Maquiagem
        "vizzela": (
            "https://www.amazon.com.br/s?k=vizzela+maquiagem"
            + _DISCOUNT_FILTER
        ),
        "dailus": (
            "https://www.amazon.com.br/s?k=dailus"
            + _DISCOUNT_FILTER
        ),
        # Cabelo
        "lola-cosmetics": (
            "https://www.amazon.com.br/s?k=lola+cosmetics"
            + _DISCOUNT_FILTER
        ),
        # Infantil
        "tenis-infantil": (
            "https://www.amazon.com.br/s?k=tenis+infantil+menino"
            + _DISCOUNT_FILTER
        ),
    }
