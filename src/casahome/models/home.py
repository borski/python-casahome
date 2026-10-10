"""Home inventory and weather models (UNVERIFIED endpoints)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ._base import CasaModel
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
    floor_number: int
    name: str
    window_count: int | None = None
    rooms: list[HomeRoom] = Field(default_factory=list)


class HomeDetails(CasaModel):
    id: str
    display_address: str
    stories: list[HomeStory] = Field(default_factory=list)


class SimpleEntity(CasaModel):
    """An inventory item (appliance, fixture, etc). Nested catalog types left loose."""

    id: str
    category_id: str
    category: str
    status: str
    type_id: str | None = None
    type: str | None = None
    type_symbol_name: str | None = None
    rooms: list[str] = Field(default_factory=list)
    stories: list[str] = Field(default_factory=list)
    images: list[Any] = Field(default_factory=list)
    manuals: list[Any] = Field(default_factory=list)
    thumbnail_url: str | None = None
    thumbnail_url_cache_key: str | None = None
    make: Any | None = None
    model: Any | None = None
    entity_properties: list[SimpleEntityProp] = Field(default_factory=list)
    associated_entity_ids: list[str] | None = None
    is_removable: bool = False


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
