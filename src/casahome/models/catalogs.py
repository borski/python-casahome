"""Inventory catalogs and recurring vendors. Vendor list items remain UNVERIFIED."""

from pydantic import Field, JsonValue, RootModel

from casahome.models._base import CasaModel
from casahome.models.home import EntityMake


class RoomType(CasaModel):
    id: str
    name: str


class RoomTypesResponse(RootModel[list[RoomType]]):
    """The room type catalog is a bare list."""


class InventoryMakesResponse(CasaModel):
    makes: list[EntityMake]


class InventoryEnumOption(CasaModel):
    """One inventory enum option. VERIFIED populated (live GET, 2026-10)."""

    id: str
    type: str
    name: str
    symbol_name: str | None = None
    category: str | None = None
    icon_url: str | None = None


class InventoryEnumsResponse(CasaModel):
    """Inventory enum catalog. VERIFIED envelope (live GET, 2026-10)."""

    enums: list[InventoryEnumOption]


class RecurringVendorCategory(CasaModel):
    id: str
    name: str
    sort_order: int
    primary_color: str
    icon_url: str
    icon_symbol_name: str
    pattern_url: str
    vendor_type_description: str


class RecurringVendorCategoriesResponse(RootModel[list[RecurringVendorCategory]]):
    """Populated category metadata observed."""


class RecurringVendor(CasaModel):
    """Minimal static SimpleDtd fields. Nested events and invoices remain opaque."""

    id: str | None = None
    home_id: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    service_category: str | None = None
    dtd_category_id: str | None = None
    rrule: str | None = None
    start_date: str | None = None
    duration_seconds: int | None = None
    next_visit_epoch_seconds: int | None = None
    payment_pending: bool | None = None
    events: list[JsonValue] = Field(default_factory=list)
    invoices: list[JsonValue] = Field(default_factory=list)


class RecurringVendorsResponse(RootModel[list[RecurringVendor]]):
    """Bare list. Empty in the saved response."""
