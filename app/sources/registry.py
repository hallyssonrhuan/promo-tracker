"""Registry: nome da fonte → classe Source. Editar quando adicionar source."""

from app.sources.promobit import PromobitSource


SOURCES: dict[str, type] = {
    "promobit": PromobitSource,
    # "pelando" entra no passo 8
}
