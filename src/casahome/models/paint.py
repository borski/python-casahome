"""Paint library models. Populated integer IDs were observed, not UUIDs."""

from casahome.models._base import CasaModel


class PaintBrand(CasaModel):
    id: int | str
    color_count: int
    name: str | None = None


class PaintCollection(CasaModel):
    id: int | str
    color_count: int
    name: str | None = None


class PaintColor(CasaModel):
    id: int | str
    color_name: str | None = None
    collection_name: str | None = None
    brand_name: str | None = None
    color_hex: str | None = None


class PaintBrandsResponse(CasaModel):
    brands: list[PaintBrand]


class PaintCollectionsResponse(CasaModel):
    collections: list[PaintCollection]


class PaintColorsResponse(CasaModel):
    colors: list[PaintColor]


class PaintSearchResponse(CasaModel):
    results: list[PaintColor]


class InventoryPaintMatch(CasaModel):
    """One paint match. VERIFIED populated (live GET, 2026-10)."""

    id: int
    color_name: str
    brand_name: str
    color_hex: str
    closeness_percentage: float


class InventoryPaintMatchesResponse(CasaModel):
    """Paint matches. VERIFIED envelope (live GET, 2026-10). No match application."""

    matches: list[InventoryPaintMatch]
    is_manually_added: bool
