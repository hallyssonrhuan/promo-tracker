"""Registry: nome da fonte → classe Source. Adicionar entrada aqui ao criar novo source."""

from app.sources.amazon import AmazonSource
from app.sources.americanas import AmericanasSource
from app.sources.belezanaweb import BelezaNaWebSource
from app.sources.centauro import CentauroSource
from app.sources.magazineluiza import MagazineLuizaSource
from app.sources.mercadolivre import MercadoLivreSource
from app.sources.netshoes import NetshoesSource
from app.sources.pelando import PelandoSource
from app.sources.promobit import PromobitSource
from app.sources.zoom import ZoomSource


SOURCES: dict[str, type] = {
    # --- Agregadores de promoções (JSON-LD / __NEXT_DATA__ via httpx) ---
    "promobit": PromobitSource,
    "pelando": PelandoSource,
    "zoom": ZoomSource,

    # --- API pública (sem Playwright) ---
    "mercadolivre": MercadoLivreSource,

    # --- Lojas diretas (Playwright — JS rendering) ---
    "netshoes": NetshoesSource,
    "centauro": CentauroSource,
    "magazineluiza": MagazineLuizaSource,
    "americanas": AmericanasSource,
    "belezanaweb": BelezaNaWebSource,
    "amazon": AmazonSource,
}
