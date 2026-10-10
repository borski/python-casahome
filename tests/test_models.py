from __future__ import annotations

import re
from datetime import UTC
from pathlib import Path

from casahome.models import Bootstrap, RequestCard, RequestType, WeatherResponse

from .conftest import FIXTURES, load


def test_enum_known_value() -> None:
    card = RequestCard(id="1", type="handyman", title="t", emoji="x", updated_at=0)
    assert card.type is RequestType.HANDYMAN


def test_enum_unknown_value_falls_back_to_str() -> None:
    card = RequestCard(id="1", type="brand_new_kind", title="t", emoji="x", updated_at=0)
    assert card.type == "brand_new_kind"
    assert not isinstance(card.type, RequestType)


def test_camelcase_enum_values() -> None:
    w = WeatherResponse(temperature_degrees=1, temperature_units="F", condition_type="mostlyClear")
    assert w.condition_type == "mostlyClear"


def test_epoch_helpers_are_utc() -> None:
    card = RequestCard(id="1", type="concierge", title="t", emoji="x", updated_at=1_700_000_000)
    dt = card.updated_at_dt
    assert dt is not None and dt.tzinfo is UTC
    assert dt.year == 2023


def test_extra_fields_preserved() -> None:
    data = load("bootstrap.json")
    data["brand_new_field"] = {"x": 1}
    me = Bootstrap.model_validate(data)
    assert me.model_extra == {"brand_new_field": {"x": 1}}


def test_fixtures_have_no_pii() -> None:
    uuid_re = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    fake_uuid = re.compile(r"00000000-0000-4000-8000-\d{12}")
    banned = [
        re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+"),
        re.compile(r"\+1(?!555)\d{10}"),
        re.compile(r"AIza"),
        re.compile(r"X-Goog|X-Amz-|imgproxy"),
    ]
    for path in Path(FIXTURES).glob("*.json"):
        text = path.read_text()
        for found in uuid_re.findall(text):
            assert fake_uuid.fullmatch(found), f"{path.name} has a non-fake uuid {found}"
        for pattern in banned:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"


def test_home_tolerates_missing_location() -> None:
    data = load("bootstrap.json")
    for key in ("latitude", "longitude", "timezone"):
        data["homes"][0].pop(key)
    home = Bootstrap.model_validate(data).homes[0]
    assert home.latitude is None and home.timezone is None
