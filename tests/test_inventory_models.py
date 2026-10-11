"""Inventory entity typing, using synthetic data shaped like live ``inventory/v3``."""

from __future__ import annotations

from datetime import UTC
from typing import Any

import pytest
from pydantic import ValidationError

from casahome.models import (
    EntityImage,
    EntityMake,
    EntityModel,
    HomeDetailsResponse,
    SimpleEntity,
)

ENTITY_ID = "00000000-0000-4000-8000-000000000101"


def _prop(key: str, value: Any, title: str | None = None) -> dict[str, Any]:
    return {
        "id": f"prop-{key}",
        "definition_id": f"def-{key}",
        "title": title or key.replace("_", " ").title(),
        "key": key,
        "value": value,
        "data_type": "string",
        "is_required_to_publish": False,
        "format": None,
        "enum_details": None,
        "multi_enums": [],
        "enum_type": None,
        "symbol_name": key,
        "is_readonly": False,
        "help_center_article_id": None,
    }


def entity_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": ENTITY_ID,
        "category_id": "cat-1",
        "category": "Appliances",
        "type_id": "type-1",
        "type": "Cooktop",
        "type_symbol_name": "cooktop",
        "created_at": 1_700_000_000,
        "inventoried_by": "Casa",
        "status": "published",
        "failure_reason": None,
        "failure_item_label": None,
        "issues": [],
        "rooms": ["Kitchen"],
        "stories": ["Main"],
        "images": [
            {
                "id": "img-1",
                "name": "front.jpg",
                "role": "primary",
                "is_hero": True,
                "mimetype": "image/jpeg",
                "size": 1024,
                "created_at": 1_700_000_000,
                "url": "https://example.com/img",
                "url_cache_key": "k1",
                "thumbnail_url": "https://example.com/thumb",
                "thumbnail_url_cache_key": "k2",
                "cache_key": "k3",
            }
        ],
        "manuals": [{"anything": "goes"}],
        "thumbnail_url": "https://example.com/thumb",
        "thumbnail_url_cache_key": "k4",
        "catalog_make_requirement": "required",
        "catalog_model_requirement": "required",
        "catalog_model_required": True,
        "make": {"id": "make-1", "name": "Acme"},
        "model": {
            "id": "model-1",
            "name": "AC-100",
            "properties": [
                {
                    "id": "mp-1",
                    "caption": "Summary",
                    "value": "A synthetic induction cooktop.",
                    "data_type": "string",
                    "format": None,
                    "key": "summary",
                    "symbol_name": "summary",
                }
            ],
        },
        "identity": {
            "state": "verified",
            "unverified_make": None,
            "unverified_model": None,
            "candidates": [],
        },
        "entity_properties": [
            _prop("serial_number", "SN-TEST-0001"),
            _prop("year_installed", 2020),
            _prop("light_bulb_wattage", 9.5),
            _prop("light_bulb_dimmable", True),
            _prop("manufacture_date", None),
        ],
        "is_removable": True,
        "is_retypable": False,
        "removal_blocked_reason": None,
        "paint_match": None,
    }
    data.update(overrides)
    return data


def test_entity_parses_verified_fields() -> None:
    entity = SimpleEntity.model_validate(entity_payload())
    assert entity.make == EntityMake(id="make-1", name="Acme")
    assert isinstance(entity.model, EntityModel)
    assert entity.model.name == "AC-100"
    assert entity.identity is not None and entity.identity.state == "verified"
    assert entity.inventoried_by == "Casa"
    assert entity.catalog_model_required is True
    assert entity.is_retypable is False
    created = entity.created_at_dt
    assert created is not None and created.tzinfo is UTC


def test_property_values_keep_scalar_types() -> None:
    entity = SimpleEntity.model_validate(entity_payload())
    assert entity.property_value("serial_number") == "SN-TEST-0001"
    year = entity.property_value("year_installed")
    assert year == 2020 and isinstance(year, int) and not isinstance(year, bool)
    assert entity.property_value("light_bulb_wattage") == 9.5
    assert entity.property_value("light_bulb_dimmable") is True
    assert entity.property_value("manufacture_date") is None
    assert entity.property_value("does_not_exist") is None


def test_model_property_value() -> None:
    entity = SimpleEntity.model_validate(entity_payload())
    assert entity.model is not None
    assert entity.model.property_value("summary") == "A synthetic induction cooktop."
    assert entity.model.property_value("missing") is None


def test_make_and_model_may_be_null() -> None:
    entity = SimpleEntity.model_validate(entity_payload(make=None, model=None, identity=None))
    assert entity.make is None and entity.model is None and entity.identity is None


def test_image_urls_are_optional_and_ride_in_extras() -> None:
    entity = SimpleEntity.model_validate(entity_payload())
    image = entity.images[0]
    assert isinstance(image, EntityImage)
    assert image.is_hero is True
    assert image.model_extra is not None and "url" in image.model_extra
    bare = EntityImage.model_validate({"id": "img-2"})
    assert bare.name is None and bare.role is None and bare.is_hero is False


def test_minimal_legacy_entity_still_parses() -> None:
    entity = SimpleEntity.model_validate(
        {"id": ENTITY_ID, "category_id": "c", "category": "Misc", "status": "draft"}
    )
    assert entity.make is None and entity.entity_properties == []
    assert entity.property_value("serial_number") is None


def test_unknown_entity_fields_preserved() -> None:
    entity = SimpleEntity.model_validate(entity_payload(brand_new={"x": 1}))
    assert entity.model_extra == {"brand_new": {"x": 1}}


def test_non_scalar_property_value_rejected() -> None:
    payload = entity_payload(entity_properties=[_prop("odd", {"nested": 1})])
    with pytest.raises(ValidationError):
        SimpleEntity.model_validate(payload)


def test_home_details_response_with_typed_entities() -> None:
    response = HomeDetailsResponse.model_validate(
        {
            "home": {"id": "home-1", "display_address": "1 Example St", "stories": []},
            "entities": [entity_payload()],
        }
    )
    assert response.entities[0].property_value("serial_number") == "SN-TEST-0001"
