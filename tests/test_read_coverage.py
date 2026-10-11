"""Synthetic SDK contracts. Never read credentials or contact a server."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
from pydantic import BaseModel

from casahome import CasaApi, CasaClient, CasaResponseError, is_unverified
from casahome.models import (
    AutopilotCategory,
    CasaAIBootstrapResponse,
    CompletedRequestsResponse,
    NotificationSettingsResponse,
    SimpleEntity,
    TodoReadDetail,
    UtilitiesInsightsResponse,
    VehiclesResponse,
    WorkDocumentSourceResponse,
)

H = "/protected/home/home-test"
MH = "/protected/member/home/home-test"


@dataclass
class ReadClient:
    payload: Any
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    async def get(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        self.calls.append((path, params or {}))
        return deepcopy(self.payload)


def make_api(payload: Any) -> tuple[CasaApi, ReadClient]:
    client = ReadClient(payload)
    return CasaApi(cast(CasaClient, client), device_id="test-device"), client


TODO: dict[str, Any] = {
    "id": "todo-test",
    "title": "Example repair",
    "emoji": "x",
    "original_text": "Example repair",
    "prepared_brief": "Synthetic brief",
    "status": "future-status",
    "creator_role": "future-role",
    "created_at": 1,
    "updated_at": 2,
    "is_suggested": True,
    "flagged_for_support": False,
    "attachments": [
        {
            "id": "attachment-test",
            "name": "example.jpg",
            "mimetype": "image/jpeg",
            "size": 42,
            "url": "https://example.invalid/photo?signature=fake",
            "thumbnail_url": "https://example.invalid/thumb",
            "cache_key": "test-cache",
            "future_attachment_field": {"value": 3},
        }
    ],
    "question_rounds": [],
    "destination": None,
    "can_delete": False,
    "future_todo_field": "retained",
}
ENTITY = {
    "id": "entity-test",
    "category_id": "category-test",
    "category": "Example",
    "status": "published",
    "entity_properties": [
        {
            "id": "prop-test",
            "definition_id": "def-test",
            "title": "Serial",
            "key": "serial_number",
            "value": "SYNTHETIC-ONLY",
        }
    ],
}
COLOR = {
    "id": 101,
    "color_name": "Example color",
    "collection_name": "Example collection",
    "brand_name": "Example brand",
    "color_hex": "#123456",
}
IMAGE = {
    "id": "image-test",
    "image_url": "https://example.invalid/image",
    "cache_key": "test-cache",
    "is_current": False,
}
CATEGORY: dict[str, Any] = {
    "category_id": "category-test",
    "category_title": "Example category",
    "category_description": "Synthetic description",
    "category_rendering_type": "future",
    "plans": [
        {
            "plan_id": "plan-test",
            "plan_template_id": "template-test",
            "title": "Example plan",
            "subtitle": "Example subtitle",
            "description": "Example description",
            "applies_to": "room_types",
            "type": "future-type",
            "enabled": False,
            "requirement": {
                "kind": "room_property",
                "noun_with_article": "a room",
                "options": [{"type_id": "type-test", "name": "Example room"}],
                "property": {
                    "definition_id": "def-test",
                    "entity_type_id": "type-test",
                    "title": "Example property",
                },
                "room_property": {
                    "definition_id": "def-room-test",
                    "title": "Example",
                    "data_type": "boolean",
                    "symbol_name": None,
                },
                "room_candidates": [
                    {
                        "room_id": "room-test",
                        "name": "Example room",
                        "story_name": "Example story",
                        "story_floor_number": 1,
                        "duration_minutes": 15,
                        "property_value": None,
                        "price_usd_cents": 800,
                    }
                ],
            },
            "illustration": {"url": None, "url_cache_key": None, "bg_color": "example"},
            "asap_schedule_description": "Example schedule",
            "pricing_policies": [
                {"symbol_name": "x", "title": "Example policy", "description": "Example terms"}
            ],
            "fulfillment_policy": "Example fulfillment",
            "handyman_credit_policy": None,
            "savings_percentage": 0,
            "cadence_options": ["future-cadence"],
            "default_cadence": "future-cadence",
            "selected_cadence": None,
            "next_projected_occurrence_range_start": "2030-01-01",
            "next_projected_occurrence_range_end": "2030-01-02",
            "home_association": {"id": "home-assoc-test", "duration_minutes": 15},
            "room_associations": [
                {
                    "id": "room-assoc-test",
                    "room_id": "room-test",
                    "room_name": "Example room",
                    "room_story_name": "Example story",
                    "duration_minutes": 15,
                    "enabled": None,
                }
            ],
            "entity_associations": [
                {
                    "id": "entity-assoc-test",
                    "entity_id": "entity-test",
                    "entity_make": "Example make",
                    "entity_model": "Example model",
                    "duration_minutes": 15,
                    "enabled": None,
                }
            ],
            "future_plan_field": {"flag": True},
        }
    ],
    "ineligible_plans": [
        {
            "plan_template_id": "ineligible-test",
            "title": "Example",
            "subtitle": "Example",
            "description": "Example",
            "type": "future",
            "fulfillment_policy": "Example",
            "illustration": {"bg_color": "example"},
            "requirement": {"kind": "entity_property", "options": []},
        }
    ],
    "future_category_field": [1, 2],
}


@dataclass(frozen=True)
class ReadCase:
    name: str
    path: str
    payload: Any
    args: tuple[Any, ...] = ("home-test",)
    kwargs: dict[str, Any] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)


CASES = [
    ReadCase(
        "completed_requests",
        f"{H}/requests_tab/completed",
        {
            "kind": "requests",
            "items": [],
            "pagination": {"page": 1, "page_size": 100, "total_count": 0, "total_pages": 0},
        },
        args=("home-test", 1),
        query={"kind": "requests", "page": "1", "page_size": "100"},
    ),
    ReadCase(
        "autopilot_plans",
        f"{H}/autopilot/list/v2",
        [CATEGORY],
        query={"requirement_kinds": "entity_property,room_property"},
    ),
    ReadCase(
        "inventory_service_history",
        f"{H}/inventory/service_history",
        {"autopilot_plans": [], "history_items": []},
        args=("home-test", "room", "room-test"),
        query={"inventory_target_type": "room", "inventory_target_id": "room-test"},
    ),
    ReadCase(
        "calendar_busy",
        f"{H}/calendar_busy",
        {"blocks": [], "google_status": "future"},
        args=("home-test", 1, 2),
        query={"start_time": "1", "end_time": "2"},
    ),
    ReadCase(
        "room_image_options",
        f"{MH}/room/room-test/image/options",
        {"matterport_images": [IMAGE], "member_image": None},
        args=("home-test", "room-test"),
    ),
    ReadCase(
        "room_image_candidates",
        f"{MH}/room_image_candidates",
        {"matterport_images": [IMAGE], "member_image": None},
    ),
    ReadCase(
        "paint_search",
        f"{H}/paint/library/search",
        {"results": [COLOR]},
        args=("home-test", "Example"),
        query={"q": "Example"},
    ),
    ReadCase(
        "paint_brands",
        f"{H}/paint/library/brands",
        {"brands": [{"id": 101, "name": "Example brand", "color_count": 7}]},
    ),
    ReadCase(
        "paint_collections",
        f"{H}/paint/library/brands/101/collections",
        {"collections": [{"id": 202, "name": "Example collection", "color_count": 7}]},
        args=("home-test", 101),
    ),
    ReadCase(
        "paint_colors",
        f"{H}/paint/library/collections/202/colors",
        {"colors": [COLOR]},
        args=("home-test", 202),
    ),
    ReadCase(
        "todo_details", f"{H}/todos/todo-test", {"todo": TODO}, args=("home-test", "todo-test")
    ),
    ReadCase("suggested_todos", f"{H}/suggested_todos", {"suggested_todos": [TODO]}),
    ReadCase(
        "work_document_source",
        f"{H}/work_document_source",
        {"source": None},
        kwargs={"todo_id": "todo-test"},
        query={"todo_id": "todo-test"},
    ),
    ReadCase(
        "inventory_item", f"{MH}/entity/entity-test/v2", ENTITY, args=("home-test", "entity-test")
    ),
    ReadCase(
        "documents", f"{H}/documents", {"documents": [], "next_cursor": None}, query={"limit": "30"}
    ),
    ReadCase(
        "document_types",
        f"{H}/documents/types",
        {
            "types": [{"key": "example", "label": "Example type", "description": "Synthetic type"}],
            "max_file_size_bytes": 100,
            "max_organization_size_bytes": None,
            "max_files_per_upload": 2,
            "allowed_mimetypes": ["application/pdf"],
        },
    ),
    ReadCase(
        "casa_ai_bootstrap",
        f"{H}/casa_ai",
        {
            "conversation": {"id": "conversation-test"},
            "messages": {"items": [], "next_cursor": None},
            "active_response": None,
            "starter_suggestions": [{"prompt": "Example prompt", "system_image": "x"}],
            "event_cursor": "opaque-test-cursor",
            "send_to_human_target_message_id": None,
        },
    ),
    ReadCase("casa_ai_messages", f"{H}/casa_ai/messages", {"items": [], "next_cursor": None}),
    ReadCase(
        "schedule_preferences",
        f"{H}/schedule_preferences",
        {
            "days_of_week": [{"day_of_week": 1, "label": "M", "enabled": False}],
            "times_of_day": [
                {
                    "id": "window-test",
                    "window_title": "Example",
                    "window_time_range": "Example range",
                    "enabled": True,
                }
            ],
        },
    ),
    ReadCase(
        "notification_settings",
        f"{H}/notification_settings",
        {
            "groups": [
                {
                    "key": "future",
                    "display_name": "Example group",
                    "sort_order": 1,
                    "types": [
                        {
                            "key": "example",
                            "display_name": "Example type",
                            "description": "Example",
                            "sort_order": 1,
                            "channels": [
                                {
                                    "channel": "future",
                                    "enabled": True,
                                    "default_enabled": False,
                                    "required": True,
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    ),
    ReadCase(
        "onboarding_availability",
        f"{H}/onboarding/availability",
        {
            "message": "Example",
            "number_of_required_vendors": 1,
            "estimated_visit_duration_seconds": 60,
            "timezone": "UTC",
            "available_slots": [{"start_time": 1, "vendor_ids": ["vendor-test"]}],
        },
    ),
    ReadCase(
        "onboarding_details_typed",
        f"{H}/onboarding/details",
        {"calendar_events": [{"id": "event-test", "start_at": 1, "end_at": 2}]},
    ),
    ReadCase("vehicles", f"{H}/vehicles", {"vehicles": []}),
    ReadCase("utilities_insights", f"{H}/utilities/insights", {"services": []}),
    ReadCase(
        "room_types",
        "/protected/inventory/room_types/list",
        [{"id": "room-type-test", "name": "Example room type"}],
        args=(),
    ),
    ReadCase(
        "home_members",
        f"{H}/home_members/list",
        {
            "members": [
                {
                    "id": "member-test",
                    "first_name": "Example",
                    "last_name": "Person",
                    "user_id": None,
                    "gender": None,
                    "date_of_birth": None,
                    "expires_at": None,
                }
            ]
        },
    ),
    ReadCase(
        "purchases",
        f"{H}/purchases",
        {
            "context_title": "Example home",
            "pending_purchase_approvals": [],
            "approved_purchases": [],
            "purchased_items": [],
            "non_purchase_invoices": [],
            "next_package_pickup_by": 3,
        },
    ),
    ReadCase(
        "property_taxes",
        f"{H}/property_taxes",
        {
            "next_tax_bill_release_at": None,
            "refresh": {"status": "future", "next_fetch_at": 3},
            "reports": [],
        },
    ),
    ReadCase(
        "matterport_images",
        f"{H}/matterport/images",
        [
            {
                "id": "image-test",
                "image_url": "https://example.invalid/image",
                "cache_key": "test-cache",
                "is_home_hero_image": False,
            }
        ],
    ),
    ReadCase(
        "release_notes",
        "/protected/release_notes/member_ios/all",
        {
            "data": [
                {
                    "id": "release-test",
                    "title": "Example release",
                    "version": "example-version",
                    "date": 1,
                    "min_build_number": 1,
                    "max_build_number": None,
                    "hero_image_url": None,
                    "sections": [
                        {"id": "section-test", "content": "Example content", "title": None}
                    ],
                }
            ]
        },
        args=(),
    ),
    ReadCase("access_preferences", f"{H}/access_preferences", {"home_id": "home-test"}),
    ReadCase(
        "calendar_sync",
        f"{H}/calendar_sync",
        {
            "home_id": "home-test",
            "user_oauth_connected": False,
            "user_oauth_insufficient_scope": False,
            "calendar_sync_active": False,
            "has_active_syncs_in_other_homes": False,
            "available_calendars": [],
            "display_calendars": [],
            "sync_progress": None,
        },
    ),
    ReadCase(
        "inventory_makes",
        "/protected/member/inventory/makes/entity_type/type-test",
        {"makes": [{"id": "make-test", "name": "Example make"}]},
        args=("type-test",),
    ),
    ReadCase(
        "recurring_vendor_categories",
        f"{H}/dtd/categories",
        [
            {
                "id": "category-test",
                "name": "Example category",
                "sort_order": 1,
                "primary_color": "#123456",
                "icon_url": "https://example.invalid/icon",
                "icon_symbol_name": "x",
                "pattern_url": "https://example.invalid/pattern",
                "vendor_type_description": "Example",
            }
        ],
    ),
    ReadCase("recurring_vendors", f"{H}/dtd/list", []),
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_explicit_get_contract(case: ReadCase) -> None:
    api, client = make_api(case.payload)
    result = await getattr(api, case.name)(*case.args, **case.kwargs)
    assert isinstance(result, (BaseModel, list))
    assert client.calls == [(case.path, case.query)]
    assert not is_unverified(getattr(api, case.name))
    doc = getattr(api, case.name).__doc__ or ""
    assert doc.startswith("VERIFIED")
    assert "2026-10" in doc


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_every_new_get_wraps_schema_errors(case: ReadCase) -> None:
    api, _ = make_api({"error": "synthetic failure, not the expected envelope"})
    with pytest.raises(CasaResponseError, match="Unexpected") as error:
        await getattr(api, case.name)(*case.args, **case.kwargs)
    assert "synthetic failure" not in str(error.value)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_unknown_fields_survive(case: ReadCase) -> None:
    payload = deepcopy(case.payload)
    if isinstance(payload, list):
        if not payload:
            return  # Empty bare list has no envelope on which to attach an extra.
        payload[0]["future_field"] = {"nested": [1, None]}
    else:
        payload["future_field"] = {"nested": [1, None]}
    api, _ = make_api(payload)
    result = await getattr(api, case.name)(*case.args, **case.kwargs)
    model = result[0] if isinstance(result, list) else result
    assert model.model_extra["future_field"] == {"nested": [1, None]}


async def test_todo_read_fields_are_typed_without_changing_create_model() -> None:
    api, client = make_api({"todo": TODO})
    todo = (await api.todo_details("home-test", "todo-test")).todo
    assert isinstance(todo, TodoReadDetail)
    assert todo.attachments[0].size == 42
    assert todo.attachments[0].model_extra == {"future_attachment_field": {"value": 3}}
    assert todo.status == "future-status"
    assert todo.creator_role == "future-role"
    assert todo.model_extra == {"future_todo_field": "retained"}
    assert len(client.calls) == 1  # No attachment URL fetch.


async def test_autopilot_nested_variants() -> None:
    api, _ = make_api([CATEGORY])
    (category,) = await api.autopilot_plans("home-test")
    assert isinstance(category, AutopilotCategory)
    plan = category.plans[0]
    assert plan.requirement is not None
    assert plan.requirement.room_candidates is not None
    assert plan.requirement.room_candidates[0].property_value is None
    assert plan.requirement.property is not None
    assert plan.requirement.property.entity_type_id == "type-test"
    assert plan.home_association is not None and plan.home_association.duration_minutes == 15
    assert plan.entity_associations[0].entity_make == "Example make"
    assert plan.pricing_policies[0].title == "Example policy"
    assert plan.model_extra == {"future_plan_field": {"flag": True}}
    assert category.ineligible_plans[0].requirement.kind == "entity_property"


async def test_inventory_item_reuses_simple_entity() -> None:
    api, _ = make_api(ENTITY)
    result = await api.inventory_item("home-test", "entity-test")
    assert isinstance(result, SimpleEntity)
    assert result.property_value("serial_number") == "SYNTHETIC-ONLY"


async def test_completed_request_populated_static_fallback() -> None:
    payload = deepcopy(CASES[0].payload)
    payload["items"] = [
        {
            "id": "request-test",
            "type": "future-type",
            "title": "Example",
            "emoji": "x",
            "updated_at": 1,
            "extra": "retained",
        }
    ]
    api, _ = make_api(payload)
    result = await api.completed_requests("home-test", 1)
    assert isinstance(result, CompletedRequestsResponse)
    assert result.items[0].type == "future-type"
    assert result.items[0].model_extra == {"extra": "retained"}


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        (None, None),
        ("", None),
        (" \t ", None),
        ("  Example repair  ", "Example repair"),
    ],
)
async def test_completed_request_search(search: str | None, expected: str | None) -> None:
    api, client = make_api(CASES[0].payload)
    await api.completed_requests("home-test", 2, 25, search)
    params = {"kind": "requests", "page": "2", "page_size": "25"}
    if expected is not None:
        params["search"] = expected
    assert client.calls == [(f"{H}/requests_tab/completed", params)]


@pytest.mark.parametrize("selector", ["todo_id", "task_id", "request_id"])
async def test_work_source_selectors(selector: str) -> None:
    api, client = make_api({"source": None})
    result = await api.work_document_source("home-test", **{selector: "work-test"})
    assert result.source is None
    assert client.calls == [(f"{H}/work_document_source", {selector: "work-test"})]


@pytest.mark.parametrize(
    "selectors",
    [
        {},
        {"todo_id": "a", "task_id": "b"},
        {"todo_id": "a", "request_id": "b"},
        {"task_id": "a", "request_id": "b"},
        {"todo_id": "a", "task_id": "b", "request_id": "c"},
    ],
)
async def test_work_source_requires_exactly_one(selectors: dict[str, str]) -> None:
    api, client = make_api({"source": None})
    with pytest.raises(ValueError, match="exactly one"):
        await api.work_document_source("home-test", **selectors)
    assert not client.calls


async def test_document_filters_and_opaque_cursor() -> None:
    api, client = make_api({"documents": [], "next_cursor": "new-cursor"})
    result = await api.documents(
        "home-test",
        cursor="opaque/+=?",
        limit=7,
        q="a & b",
        document_type="example",
        sort="caller-supplied-value",
    )
    assert result.next_cursor == "new-cursor"
    assert client.calls == [
        (
            f"{H}/documents",
            {
                "cursor": "opaque/+=?",
                "limit": "7",
                "q": "a & b",
                "document_type": "example",
                "sort": "caller-supplied-value",
            },
        )
    ]


async def test_ai_optional_pagination() -> None:
    api, client = make_api({"items": [], "next_cursor": None})
    await api.casa_ai_messages("home-test", limit=7, before="opaque/+=?")
    assert client.calls == [(f"{H}/casa_ai/messages", {"limit": "7", "before": "opaque/+=?"})]


async def test_busy_aware_bounds_and_google_ids() -> None:
    api, client = make_api({"blocks": [], "google_status": "not_connected"})
    start = datetime(2026, 1, 1, tzinfo=UTC)
    await api.calendar_busy(
        "home-test",
        start,
        start + timedelta(hours=1),
        google_calendar_ids=["example@group.invalid", "other@example.invalid"],
    )
    assert client.calls == [
        (
            f"{H}/calendar_busy",
            {
                "start_time": "1767225600",
                "end_time": "1767229200",
                "google_calendar_ids": "example@group.invalid,other@example.invalid",
            },
        )
    ]


@pytest.mark.parametrize("target_type", ["home", "room", "entity"])
async def test_service_history_target_types(target_type: str) -> None:
    api, client = make_api({"autopilot_plans": [], "history_items": []})
    await api.inventory_service_history("home-test", cast(Any, target_type), "target-test")
    assert client.calls[0][1]["inventory_target_type"] == target_type


@pytest.mark.parametrize("value", [101, "00101", "catalog-test", "item.test", "item~test"])
async def test_catalog_ids_preserved(value: int | str) -> None:
    api, client = make_api({"collections": []})
    await api.paint_collections("home-test", value)
    assert client.calls[0][0] == f"{H}/paint/library/brands/{value}/collections"
    client.payload = {"colors": []}
    await api.paint_colors("home-test", value)
    assert client.calls[1][0] == f"{H}/paint/library/collections/{value}/colors"


BAD_IDS = [
    "",
    "/",
    "a/b",
    "a?b",
    "a#b",
    "a\\b",
    ".",
    "..",
    "%2f",
    "%252f",
    "../other",
    "a\x00b",
    "a\nb",
    "a\x7fb",
    "a b",
    "a\x85b",
    True,
    1.5,
    None,
]


@pytest.mark.parametrize("case", [case for case in CASES if case.args], ids=lambda case: case.name)
@pytest.mark.parametrize("bad_id", BAD_IDS)
async def test_new_methods_reject_unsafe_primary_identifier(case: ReadCase, bad_id: Any) -> None:
    api, client = make_api(case.payload)
    with pytest.raises(ValueError, match="identifier"):
        await getattr(api, case.name)(bad_id, *case.args[1:], **case.kwargs)
    assert not client.calls


@pytest.mark.parametrize(
    "method",
    ["inventory_item", "todo_details", "room_image_options", "paint_collections", "paint_colors"],
)
@pytest.mark.parametrize("bad_id", BAD_IDS)
async def test_new_methods_reject_unsafe_secondary_identifier(method: str, bad_id: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="identifier"):
        await getattr(api, method)("home-test", bad_id)
    assert not client.calls


@pytest.mark.parametrize("bad_id", BAD_IDS)
async def test_query_target_ids_are_safe(bad_id: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="identifier"):
        await api.inventory_service_history("home-test", "entity", bad_id)
    with pytest.raises(ValueError, match="identifier"):
        await api.work_document_source(
            "home-test", todo_id=bad_id if bad_id is not None else "unsafe/id"
        )
    assert not client.calls


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "7"])
async def test_positive_pagination_validated_before_io(value: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="positive integer"):
        await api.completed_requests("home-test", value)
    with pytest.raises(ValueError, match="positive integer"):
        await api.completed_requests("home-test", 1, value)
    with pytest.raises(ValueError, match="positive integer"):
        await api.documents("home-test", limit=value)
    with pytest.raises(ValueError, match="positive integer"):
        await api.casa_ai_messages("home-test", limit=value)
    assert not client.calls


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (2, 1),
        (1, 1),
        (True, 2),
        (1.5, 2),
        (1, False),
        (datetime(2026, 1, 1), datetime(2026, 1, 2)),
    ],
)
async def test_busy_invalid_bounds(start: Any, end: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError):
        await api.calendar_busy("home-test", start, end)
    assert not client.calls


class NoOffsetZone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> str:
        return "NoOffsetZone"


async def test_busy_rejects_tzinfo_without_offset() -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="timezone-aware"):
        await api.calendar_busy("home-test", datetime(2026, 1, 1, tzinfo=NoOffsetZone()), 2)
    assert not client.calls


@pytest.mark.parametrize(
    "ids", [[], [""], [" "], ["a,b"], ["a\nb"], ["a\x7fb"], ["a\x85b"], [None], [7], "bare-string"]
)
async def test_busy_rejects_ambiguous_google_ids(ids: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="google_calendar_ids"):
        await api.calendar_busy("home-test", 1, 2, google_calendar_ids=ids)
    assert not client.calls


@pytest.mark.parametrize("kinds", [[], ["unknown"], "entity_property"])
async def test_autopilot_requirement_kinds_rejected(kinds: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="requirement_kinds"):
        await api.autopilot_plans("home-test", kinds)
    assert not client.calls


async def test_invalid_target_type_rejected() -> None:
    api, client = make_api({})
    with pytest.raises(ValueError, match="target_type"):
        await api.inventory_service_history("home-test", cast(Any, "unknown"), "target-test")
    assert not client.calls


async def test_onboarding_raw_compatibility_and_typed_304() -> None:
    payload = {"calendar_events": [{"id": "event-test", "start_at": 1, "end_at": 2}]}
    api, client = make_api(payload)
    assert await api.onboarding_details("home-test") == payload
    typed = await api.onboarding_details_typed("home-test")
    assert typed is not None and typed.calendar_events[0].id == "event-test"
    client.payload = None
    assert await api.onboarding_details("home-test") is None
    assert await api.onboarding_details_typed("home-test") is None


def test_notification_metadata_nested_models() -> None:
    payload = next(case.payload for case in CASES if case.name == "notification_settings")
    settings = NotificationSettingsResponse.model_validate(payload)
    assert settings.groups[0].types[0].channels[0].required


def test_public_model_exports() -> None:
    import casahome.models as models

    assert len(models.__all__) == len(set(models.__all__))
    for name in models.__all__:
        assert getattr(models, name) is not None


def assert_synthetic_capture_payload(value: Any, key: str = "") -> None:
    """Guard fixture bodies so only synthetic identity values appear."""
    if isinstance(value, dict):
        for child_key, child in value.items():
            assert_synthetic_capture_payload(child, child_key)
    elif isinstance(value, list):
        for child in value:
            assert_synthetic_capture_payload(child, key.removesuffix("s"))
    elif isinstance(value, str):
        assert not re.search(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", value)
        if key == "id" or key.endswith("_id"):
            assert value.endswith("-test"), "New fixture identifiers must be synthetic"
        if key in {"first_name", "last_name"}:
            assert value in {"Example", "Person"}, "New member names must be synthetic"
        if value.startswith(("https://", "http://")):
            assert (urlsplit(value).hostname or "").endswith(".invalid")
        if key in {"email", "phone"}:
            assert key == "email" and value.endswith(".invalid")
        if key == "value":
            assert value.startswith("SYNTHETIC-"), "Fixture serials must be explicit placeholders"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_new_fixtures_contain_only_synthetic_identity_and_urls(case: ReadCase) -> None:
    assert_synthetic_capture_payload(case.payload)


@pytest.mark.parametrize(
    "name",
    [
        "completed_requests",
        "autopilot_plans",
        "paint_search",
        "todo_details",
        "notification_settings",
        "documents",
        "casa_ai_bootstrap",
    ],
)
async def test_malformed_nested_models_raise_library_error(name: str) -> None:
    case = next(case for case in CASES if case.name == name)
    payload = deepcopy(case.payload)
    match name:
        case "completed_requests":
            payload["pagination"]["page"] = {"secret": "synthetic-private-text"}
        case "autopilot_plans":
            payload[0]["plans"][0]["room_associations"] = "not-a-list"
        case "paint_search":
            payload["results"][0]["id"] = {"secret": "synthetic-private-text"}
        case "todo_details":
            payload["todo"]["attachments"][0]["size"] = "synthetic-private-text"
        case "notification_settings":
            payload["groups"][0]["types"][0]["channels"] = "not-a-list"
        case "documents":
            payload["documents"] = [{"size_bytes": "synthetic-private-text"}]
        case "casa_ai_bootstrap":
            payload["messages"]["items"] = "not-a-list"
    api, _ = make_api(payload)
    with pytest.raises(CasaResponseError, match="validation error") as error:
        await getattr(api, name)(*case.args, **case.kwargs)
    assert "synthetic-private-text" not in str(error.value)


def test_static_optional_models_preserve_known_and_opaque_fields() -> None:
    vehicles = VehiclesResponse.model_validate(
        {
            "vehicles": [
                {
                    "id": "vehicle-test",
                    "display_name": "Example vehicle",
                    "powertrain": {"type": "future", "display_name": "Example powertrain"},
                    "readings": {"future_sensor": {"value": 3, "unit": "example"}},
                    "future_vehicle_field": [1, None],
                }
            ]
        }
    )
    assert vehicles.vehicles[0].readings == {"future_sensor": {"value": 3, "unit": "example"}}
    assert vehicles.vehicles[0].model_extra == {"future_vehicle_field": [1, None]}
    assert vehicles.vehicles[0].powertrain is not None
    assert vehicles.vehicles[0].powertrain.type == "future"

    utilities = UtilitiesInsightsResponse.model_validate(
        {
            "services": [
                {
                    "id": "service-test",
                    "service_type": "future-service",
                    "usage_unit": "future-unit",
                    "statements": [{"id": "statement-test", "service_usage_amount": 2.5}],
                    "interval_graphs": [
                        {
                            "id": "graph-test",
                            "period": "future",
                            "windows": [
                                {
                                    "id": "window-test",
                                    "usage_values": [1.0, 2.5],
                                    "future_window_field": True,
                                }
                            ],
                        }
                    ],
                    "accounts": [{"id": "account-test", "credential_status": "future"}],
                }
            ]
        }
    )
    assert utilities.services[0].statements[0].service_usage_amount == 2.5
    window = utilities.services[0].interval_graphs[0].windows[0]
    assert window.usage_values == [1.0, 2.5]
    assert window.model_extra == {"future_window_field": True}

    source = WorkDocumentSourceResponse.model_validate(
        {
            "source": {
                "document_id": "document-test",
                "available": True,
                "citations": [
                    {"page_index": 0, "excerpt": "Example excerpt", "future": "retained"}
                ],
            }
        }
    )
    assert source.source is not None
    assert source.source.citations[0].page_index == 0
    assert source.source.citations[0].model_extra == {"future": "retained"}


def test_ai_static_parts_remain_json_without_inventing_union_tags() -> None:
    response = CasaAIBootstrapResponse.model_validate(
        {
            "conversation": None,
            "starter_suggestions": [],
            "messages": {
                "items": [
                    {
                        "id": "message-test",
                        "sender_role": "future",
                        "parts": [
                            {
                                "id": "part-test",
                                "payload": {"future_tag": {"nested": [1, None]}},
                            }
                        ],
                        "feedback": {"rating": "future-rating"},
                    }
                ]
            },
            "active_response": {
                "message_id": "message-test",
                "parts": [
                    {
                        "id": "active-part-test",
                        "payload": ["example", {"future": True}],
                    }
                ],
            },
        }
    )
    message = response.messages.items[0]
    assert message.parts[0].payload == {"future_tag": {"nested": [1, None]}}
    assert message.feedback is not None and message.feedback.rating == "future-rating"
    assert response.active_response is not None
    assert response.active_response.parts[0].payload == ["example", {"future": True}]
