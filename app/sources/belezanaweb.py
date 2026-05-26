"""Source: Beleza na Web (belezanaweb.com.br).

Especializada em beleza/cosméticos — cobre Vizzela, Dailus e Lola Cosmetics
diretamente nas páginas de marca. Usa Playwright para Next.js SSR.
"""

from app.sources.base_playwright import PlaywrightSource


class BelezaNaWebSource(PlaywrightSource):
    nome = "belezanaweb"
    _default_loja = "Beleza na Web"
    _base_url = "https://www.belezanaweb.com.br"

    URLS: dict[str, str] = {
        "vizzela": "https://www.belezanaweb.com.br/vizzela/",
        "dailus": "https://www.belezanaweb.com.br/dailus/",
        "lola-cosmetics": "https://www.belezanaweb.com.br/lola-cosmetics/",
        "lola-shampoo": "https://www.belezanaweb.com.br/lola-cosmetics/shampoo/",
        "lola-condicionador": "https://www.belezanaweb.com.br/lola-cosmetics/condicionador/",
    }
