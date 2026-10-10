from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from casahome import CasaApi, CasaResponseError, is_unverified
from casahome.models import CreateTodoBody, MemberSimpleHomeStatus

from .conftest import HOME_ID, FakeServer, load

pytestmark = pytest.mark.usefixtures("token_ok")
H = f"/protected/member/home/{HOME_ID}"


async def test_bootstrap(server: FakeServer, api: CasaApi) -> None:
    server.add("POST", "/protected/member/bootstrap", payload=load("bootstrap.json"))
    me = await api.bootstrap()
    assert me.homes[0].id == HOME_ID
    assert me.homes[0].status is MemberSimpleHomeStatus.ONBOARDING
    assert me.homes[0].plan_state == "never_paid"
    assert me.homes[0].badge_counts is not None
    assert me.homes[0].badge_counts.features["mailbox"] == 0
    assert me.app_update is not None and not me.app_update.force_update_required

    (call,) = server.calls("POST", "/protected/member/bootstrap")
    device = json.loads(call.body)["user_device"]
    assert set(device) == {
        "device_id",
        "device_name",
        "system_name",
        "system_version",
        "model",
        "language",
        "timezone",
        "app",
        "app_version",
        "app_build",
        "fcm_token",
        "voip_token",
    }
    assert device["app"] == "member_ios"
    assert "/" in device["timezone"] or device["timezone"] == "UTC"


def test_bootstrap_device_id_stable(api: CasaApi) -> None:
    assert api.default_device().device_id == api.default_device().device_id
    assert api.default_device().device_id == api.device_id


def test_device_id_and_timezone_injectable(client: Any) -> None:
    api = CasaApi(client, device_id="PERSISTED-ID", timezone="Europe/Oslo")
    device = api.default_device()
    assert device.device_id == "PERSISTED-ID"
    assert device.timezone == "Europe/Oslo"


async def test_onboarding_details_304(server: FakeServer, api: CasaApi) -> None:
    server.add("GET", f"/protected/home/{HOME_ID}/onboarding/details", status=304)
    assert await api.onboarding_details(HOME_ID) is None


MINIMAL: dict[str, dict[str, Any]] = {
    "home_details": {"home": {"id": "h", "display_address": "x", "stories": []}},
    "badge_counts": {"computed_at": 0, "total": 0, "features": {}},
    "weather": {"temperature_degrees": 70, "temperature_units": "F", "condition_type": "clear"},
    "requests_tab": {"requests": {}, "tasks": {}},
    "request_details": {
        "id": "r",
        "type": "concierge",
        "status": "completed",
        "title": "t",
        "emoji": "x",
        "created_at": 0,
        "updated_at": 0,
    },
    "calendar": {"events": []},
    "credits_summary": {"home_id": "h", "total_available": 0, "handyman_hourly_rate_cents": 0},
    "mailbox": {},
    "mail_items": {"mail_items": []},
    "packages": {"next_pickup_lockdown": 0, "next_pickup_start": 0, "next_pickup_end": 0},
}

CASES: list[tuple[str, tuple[Any, ...], str, str]] = [
    ("home_details", (HOME_ID,), "GET", f"{H}/inventory/v3"),
    ("badge_counts", (HOME_ID,), "GET", f"{H}/badge_counts"),
    ("weather", (HOME_ID,), "GET", f"{H}/weather"),
    ("requests_tab", (HOME_ID,), "GET", f"{H}/requests_tab"),
    ("request_details", (HOME_ID, "req1"), "GET", f"{H}/requests/req1"),
    ("calendar", (HOME_ID, 1, 2), "GET", f"{H}/calendar"),
    ("credits_summary", (HOME_ID,), "GET", f"{H}/credits/summary"),
    ("mailbox", (HOME_ID,), "GET", f"{H}/mailbox"),
    ("mail_items", (HOME_ID,), "GET", f"{H}/mailbox/mail_items"),
    ("packages", (HOME_ID,), "GET", f"{H}/packages/v3"),
]


@pytest.mark.parametrize(("name", "args", "method", "path"), CASES)
async def test_unverified_reads(
    server: FakeServer, api: CasaApi, name: str, args: tuple[Any, ...], method: str, path: str
) -> None:
    server.add(method, path, payload=MINIMAL[name])
    result = await getattr(api, name)(*args)
    assert result is not None
    assert len(server.calls(method, path)) == 1
    assert is_unverified(getattr(api, name))


async def test_create_todo(server: FakeServer, api: CasaApi) -> None:
    todo = {
        "id": "t1",
        "title": "Fix sink",
        "emoji": "x",
        "original_text": "fix sink",
        "prepared_brief": "",
        "status": "preparing",
        "creator_role": "member",
        "created_at": 0,
        "updated_at": 0,
    }
    server.add("POST", f"{H}/todos", payload={"todo": todo})
    result = await api.create_todo(HOME_ID, CreateTodoBody(content="fix sink"))
    assert result.id == "t1"
    (call,) = server.calls("POST", f"{H}/todos")
    sent = json.loads(call.body)
    assert sent == {"content": "fix sink"}


def test_verified_methods_not_marked() -> None:
    assert not is_unverified(CasaApi.bootstrap)
    assert not is_unverified(CasaApi.onboarding_details)
    marked = {
        n for n, f in inspect.getmembers(CasaApi, inspect.iscoroutinefunction) if is_unverified(f)
    }
    assert marked == {c[0] for c in CASES} | {"create_todo"}


async def test_calendar_query_params(server: FakeServer, api: CasaApi) -> None:
    server.add("GET", f"{H}/calendar", payload={"events": []})
    await api.calendar(HOME_ID, 1, 2)
    (call,) = server.calls("GET", f"{H}/calendar")
    assert call.query == {"start_time": "1", "end_time": "2"}


async def test_schema_drift_raises_casa_error(server: FakeServer, api: CasaApi) -> None:
    server.add("POST", "/protected/member/bootstrap", payload={"homes": "not a list"})
    with pytest.raises(CasaResponseError, match="Bootstrap"):
        await api.bootstrap()


async def test_calendar_accepts_aware_datetimes(server: FakeServer, api: CasaApi) -> None:
    server.add("GET", f"{H}/calendar", payload={"events": []})
    start = datetime(2026, 1, 1, tzinfo=UTC)
    await api.calendar(HOME_ID, start, start + timedelta(days=7))
    (call,) = server.calls("GET", f"{H}/calendar")
    assert call.query == {"start_time": "1767225600", "end_time": "1767830400"}


async def test_calendar_rejects_naive_datetimes(api: CasaApi) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await api.calendar(HOME_ID, datetime(2026, 1, 1), datetime(2026, 1, 2))
