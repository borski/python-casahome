"""Home inventory and weather models.

Inventory entity fields are live-verified against ``inventory/v3`` (2026-10).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, StrictInt

from ._base import CasaModel, epoch_to_dt
from .enums import WeatherConditionField


class SimpleEntityProp(CasaModel):
    id: str
    definition_id: str
    title: str
    key: str
    value: Any = None
    data_type: str | None = None
    is_required_to_publish: bool = False
    is_readonly: bool = False
    format: str | None = None
    enum_details: Any | None = None  # TODO: unresolved type SimpleEntityEnumProp
    multi_enums: list[Any] = Field(default_factory=list)
    enum_type: str | None = None
    symbol_name: str | None = None
    help_center_article_id: str | None = None


class HomeRoom(CasaModel):
    id: str
    name: str
    is_removable: bool = False
    room_type_id: str | None = None
    image_url: str | None = None
    image_url_cache_key: str | None = None
    room_properties: list[SimpleEntityProp] = Field(default_factory=list)


class HomeStory(CasaModel):
    id: str
    floor_number: StrictInt
    name: str
    window_count: int | None = None
    rooms: list[HomeRoom] = Field(default_factory=list)


class HomeDetails(CasaModel):
    id: str
    display_address: str
    stories: list[HomeStory] = Field(default_factory=list)


PropertyValue = str | int | float | bool | None
"""Scalar value carried by entity and catalog model properties (live-verified)."""


class EntityProperty(SimpleEntityProp):
    """A typed property on an inventory entity, e.g. ``serial_number``.

    Same wire shape as :class:`SimpleEntityProp`, but the value is narrowed to
    the scalar types observed live on ``inventory/v3``.
    """

    value: PropertyValue = None


class EntityMake(CasaModel):
    id: str
    name: str


class ModelProperty(CasaModel):
    """A catalog property on a make/model, e.g. key ``summary``."""

    id: str
    key: str
    caption: str | None = None
    value: PropertyValue = None
    data_type: str | None = None
    format: str | None = None
    symbol_name: str | None = None


class EntityModel(CasaModel):
    id: str
    name: str
    properties: list[ModelProperty] = Field(default_factory=list)

    def property_value(self, key: str) -> PropertyValue:
        """Return the value of the first catalog property with ``key``, else None."""
        return next((p.value for p in self.properties if p.key == key), None)


class EntityIdentity(CasaModel):
    """How confidently Casa has identified the make and model."""

    state: str | None = None
    unverified_make: str | None = None
    unverified_model: str | None = None
    candidates: list[Any] = Field(default_factory=list)


class EntityImage(CasaModel):
    """Image metadata. URL and cache-key fields ride along in ``model_extra``."""

    id: str
    name: str | None = None
    role: str | None = None
    is_hero: bool = False


class SimpleEntity(CasaModel):
    """An inventory item (appliance, fixture, etc.) from ``inventory/v3``."""

    id: str
    category_id: str
    category: str
    status: str
    type_id: str | None = None
    type: str | None = None
    type_symbol_name: str | None = None
    created_at: int | None = None
    inventoried_by: str | None = None
    failure_reason: str | None = None
    failure_item_label: str | None = None
    issues: list[Any] = Field(default_factory=list)
    rooms: list[str] = Field(default_factory=list)
    stories: list[str] = Field(default_factory=list)
    images: list[EntityImage] = Field(default_factory=list)
    manuals: list[Any] = Field(default_factory=list)
    thumbnail_url: str | None = None
    thumbnail_url_cache_key: str | None = None
    catalog_make_requirement: str | None = None
    catalog_model_requirement: str | None = None
    catalog_model_required: bool | None = None
    make: EntityMake | None = None
    model: EntityModel | None = None
    identity: EntityIdentity | None = None
    entity_properties: list[EntityProperty] = Field(default_factory=list)
    associated_entity_ids: list[str] | None = None
    is_removable: bool = False
    is_retypable: bool | None = None
    removal_blocked_reason: str | None = None
    paint_match: Any | None = None

    @property
    def created_at_dt(self) -> datetime | None:
        return epoch_to_dt(self.created_at)

    def property_value(self, key: str) -> PropertyValue:
        """Return the value of the first entity property with ``key``, else None.

        Example: ``entity.property_value("serial_number")``.
        """
        return next((p.value for p in self.entity_properties if p.key == key), None)


class HomeDetailsResponse(CasaModel):
    home: HomeDetails
    entities: list[SimpleEntity] = Field(default_factory=list)
    room_entity_map: dict[str, list[str]] = Field(default_factory=dict)
    associated_entities: dict[str, list[str]] = Field(default_factory=dict)


class WeatherResponse(CasaModel):
    temperature_degrees: float
    temperature_units: str
    condition_type: WeatherConditionField
    sunrise_at: int | None = None
    sunset_at: int | None = None
