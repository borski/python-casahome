"""Synthetic static read contracts. No environment, credentials or API calls.

These fixtures test provisional SDK parsing, not server acceptance. Unknown
union shapes are deliberately represented with future-only synthetic keys.
"""

from __future__ import annotations

import inspect
import socket
import traceback
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast, get_type_hints

import pytest
from pydantic import BaseModel

from casahome import CasaApi, CasaClient, CasaResponseError, is_unverified
from casahome.models import (
    BookableHandymanTasksResponse,
    DocumentDetailsResponse,
    DocumentStructureSuggestionsResponse,
    DocumentSuggestionsResponse,
    GroupedTaskDetails,
    HelpCenterBundleResponse,
    HomeFeedResponse,
    InventoryEnumsResponse,
    InventoryPaintMatchesResponse,
    MemberAvailabilityDetail,
    MembershipDetails,
    MembershipSavings,
    ReferralCodeResponse,
    ReleaseNotesResponse,
    ScopedPurchasesResponse,
    TaskDetails,
    VendorVisitDetails,
    VisitCallsResponse,
    VisitConversation,
)

H = "/protected/home/home-test"
CANARY = "SYNTHETIC-SECRET-NOT-A-CREDENTIAL"
OPAQUE: dict[str, Any] = {"synthetic_future_variant": {"nested": [None, 7, "example"]}}
SCOPED_PURCHASES: dict[str, Any] = {
    "context_title": "Example scope",
    "pending_purchase_approvals": [{"id": "approval-test", "quantity": 2}],
    "approved_purchases": [{"id": "approved-test", "approved_at": 12}],
    "purchased_items": [{"id": "item-test", "purchased_at": 13}],
    "next_package_pickup_by": 14,
}
UPDATE: dict[str, Any] = {
    "id": "update-test",
    "message": "Example update",
    "sender_name": "Example Person",
    "sent_at": 11,
    "attachments": [],
    "future_update": {"nested": None},
}
TASK: dict[str, Any] = {
    "id": "task-test",
    "title": "Example task",
    "description": "Example description",
    "emoji": "x",
    "status": "future-status",
    "visit": {"id": "visit-test", "start_time": 10},
    "updates": [UPDATE],
    "attachments": None,
    "can_schedule_handyman_vendor_visit": False,
    "can_chat_with_concierge": False,
    "can_edit": False,
    "can_delete": False,
}
CONVERSATION: dict[str, Any] = {
    "visit_id": "visit-test",
    "thread_id": "thread-test",
    "window": {"state": "future-state", "opens_at": None, "closes_at": None},
    "calls_enabled": False,
    "live_call": None,
    "unread_count": 0,
    "participants": [
        {
            "user_id": "user-test",
            "role": "future-role",
            "display_name": "Example Person",
            "is_me": False,
            "avatar_url": "https://example.invalid/avatar",
        }
    ],
    "messages": [
        {
            "id": "message-test",
            "thread_id": "thread-test",
            "created_at": 10,
            "sender_role": "future-role",
            "sender_user_id": "user-test",
            "sender_display_name": "Example Person",
            "is_mine": False,
            "content": "Example message",
            "attachments": [],
            "parts": [OPAQUE],
        }
    ],
    "event_cursor": "synthetic/opaque+=?",
}
GROUPED: dict[str, Any] = {
    "plan": {
        "id": "plan-test",
        "title": "Example plan",
        "description": "Example description",
        "emoji": "x",
    },
    "visit": None,
    "tasks": [
        {
            "id": "task-test",
            "status": "future-status",
            "target": {
                "id": "target-test",
                "kind": "future-kind",
                "primary_label": "Example target",
                "secondary_label": "Example location",
                "symbol_name": "x",
                "image_url": "https://example.invalid/target",
            },
            "updates": [UPDATE],
        }
    ],
}
VISIT: dict[str, Any] = {
    "id": "visit-test",
    "type": "future-type",
    "status": "future-status",
    "request": {
        "id": "request-test",
        "type": "future-type",
        "status": "future-status",
        "title": "Example request",
        "emoji": "x",
        "has_unread_messages": False,
    },
    "calendar_event": {"id": "event-test", "start_time": 10, "end_time": 20},
    "vendors": [
        {
            "id": "vendor-test",
            "display_name": "Example vendor",
            "compact_display_name": "Example",
            "type": "future-type",
        }
    ],
    "task_items": [OPAQUE],
    "invoices": [
        {
            "id": "invoice-test",
            "vendor_name": "Example vendor",
            "amount_display": "Example amount",
            "user_collection_status": "future-status",
            "status": "future-status",
        }
    ],
    "purchases": [{"id": "purchase-test", "status": "future-status"}],
    "can_add_remove_items": False,
    "can_cancel": False,
    "feedback": OPAQUE,
    "conversation": {
        "window": {"state": "future-state"},
        "counterparties": [],
        "unread_count": 0,
    },
}


@dataclass(frozen=True)
class ReadCase:
    name: str
    path: str
    model: type[BaseModel]
    payload: dict[str, Any]
    args: tuple[str, ...] = ("home-test",)
    params: dict[str, str] = field(default_factory=dict)


CASES = [
    ReadCase(
        "bookable_handyman_tasks",
        f"{H}/vendor_visits/handyman/bookable_tasks",
        BookableHandymanTasksResponse,
        {
            "items": [OPAQUE],
            "current_vendor_additional_availability_minutes": None,
            "total_additional_availability_minutes": 15,
        },
    ),
    ReadCase(
        "membership_info",
        f"{H}/membership/info",
        MembershipDetails,
        {
            "name": "Example membership",
            "amount": "Example amount",
            "amount_cents": 100,
            "interval": "future-interval",
            "member_since": 10,
            "benefits": [
                {
                    "id": "benefit-test",
                    "title": "Example benefit",
                    "emoji": "x",
                    "symbol": "x",
                    "description": "Example description",
                }
            ],
        },
    ),
    ReadCase(
        "membership_savings",
        f"{H}/membership_savings",
        MembershipSavings,
        {
            "home_id": "home-test",
            "calculated_at": "example-time-string",
            "should_promote": False,
            "summary": {"total_time_saved_seconds": 60, "total_money_saved_cents": 125},
            "categories": [
                {
                    "type": "future-type",
                    "label": "Example category",
                    "color": "#123456",
                    "is_visible": True,
                    "time_saved_seconds": 60,
                    "money_saved_cents": 125,
                    "breakdown": [{"title": "Example", "value": "Example value"}],
                }
            ],
            "metadata": {"id": "metadata-test", "created_at": "example", "updated_at": "example"},
        },
    ),
    ReadCase(
        "inventory_enums",
        "/protected/member/inventory/enums/enum_type/light_fixture_type",
        InventoryEnumsResponse,
        {"enums": [{"id": "option-test", "type": "future-type", "name": "Example option"}]},
        ("light_fixture_type",),
    ),
    ReadCase(
        "release_notes_diff",
        "/protected/release_notes/member_ios/diff",
        ReleaseNotesResponse,
        {
            "data": [
                {
                    "id": "note-test",
                    "title": "Example release",
                    "version": "2026.1",
                    "date": 10,
                    "min_build_number": 698,
                    "max_build_number": None,
                    "prelude": "Example prelude",
                    "hero_image_url": "https://example.invalid/hero",
                    "sections": [
                        {
                            "id": "section-test",
                            "title": "Example section",
                            "content": "Example content",
                            "hero_image_url": None,
                        }
                    ],
                }
            ]
        },
        (),
        {"currentBuild": "698"},
    ),
    ReadCase(
        "home_feed",
        f"{H}/feed",
        HomeFeedResponse,
        {
            "cards": [
                {
                    "id": "card-test",
                    "template_id": "future-template",
                    "name": "Example card",
                    "props": {"title": "Example title", "visual_style": OPAQUE},
                    "show_starts_at_minutes_after_onboarding": 0,
                    "show_ends_at_minutes_after_onboarding": None,
                    "children": [],
                }
            ]
        },
        ("home-test",),
        {"app_build": "698"},
    ),
    ReadCase(
        "availability_request_details",
        f"{H}/availability_requests/availability-test",
        MemberAvailabilityDetail,
        {
            "availability_request": {
                "id": "availability-test",
                "request_id": "request-test",
                "home_id": "home-test",
                "status": "future-status",
                "slot_count": 1,
                "created_at": 10,
            },
            "slots": [
                {
                    "id": "slot-test",
                    "member_availability_request_id": "availability-test",
                    "start_time": 10,
                    "end_time": 20,
                }
            ],
            "home_timezone": "UTC",
            "constraints": {
                "snap_minutes": 5,
                "min_slot_minutes": 10,
                "default_duration_minutes": 20,
                "lead_time_minutes": 30,
            },
        },
        ("home-test", "availability-test"),
    ),
    ReadCase(
        "document_details",
        f"{H}/documents/document-test",
        DocumentDetailsResponse,
        {"document": {"id": "document-test", "name": "Example document", "size_bytes": 123}},
        ("home-test", "document-test"),
    ),
    ReadCase(
        "document_suggestions",
        f"{H}/documents/document-test/suggestions",
        DocumentSuggestionsResponse,
        {
            "suggestions": [
                {
                    "id": "suggestion-test",
                    "todo_id": "todo-test",
                    "title": "Example suggestion",
                    "action": "Example action",
                    "reason": "Example reason",
                    "citations": [{"page_index": 0, "excerpt": "Example excerpt"}],
                    "state": "future-state",
                    "work_deleted": False,
                }
            ],
            "analysis_status": "future-status",
            "limitations": ["Example limitation"],
        },
        ("home-test", "document-test"),
    ),
    ReadCase(
        "document_structure_suggestions",
        f"{H}/documents/document-test/structure_suggestions",
        DocumentStructureSuggestionsResponse,
        {
            "suggestions": [
                {
                    "id": "suggestion-test",
                    "section": "Example section",
                    "title": "Example structure",
                    "current_values": ["Example value"],
                    "current_label": "Example current",
                    "proposed_label": "Example proposed",
                    "reason": "Example reason",
                    "state": "future-state",
                    "changed_since_analysis": False,
                    "citations": [],
                }
            ]
        },
        ("home-test", "document-test"),
    ),
    ReadCase(
        "inventory_paint_matches",
        f"{H}/entity/entity-test/paint/library/match",
        InventoryPaintMatchesResponse,
        {
            "matches": [
                {
                    "id": 101,
                    "color_name": "Example color",
                    "brand_name": "Example brand",
                    "color_hex": "#123456",
                    "closeness_percentage": 95.5,
                }
            ],
            "is_manually_added": False,
        },
        ("home-test", "entity-test"),
    ),
    ReadCase(
        "request_purchases",
        f"{H}/requests/request-test/purchases",
        ScopedPurchasesResponse,
        SCOPED_PURCHASES,
        ("home-test", "request-test"),
    ),
    ReadCase("task_details", f"{H}/tasks/task-test", TaskDetails, TASK, ("home-test", "task-test")),
    ReadCase(
        "vendor_visit_details",
        f"{H}/vendor_visits/visit-test",
        VendorVisitDetails,
        VISIT,
        ("home-test", "visit-test"),
    ),
    ReadCase(
        "vendor_visit_autopilot_plan",
        f"{H}/vendor_visits/visit-test/autopilot_plans/plan-test",
        GroupedTaskDetails,
        GROUPED,
        ("home-test", "visit-test", "plan-test"),
    ),
    ReadCase(
        "vendor_visit_calls",
        f"{H}/vendor_visits/visit-test/calls",
        VisitCallsResponse,
        {
            "calls": [
                {
                    "id": "call-test",
                    "vendor_visit_id": "visit-test",
                    "status": "future-status",
                    "started_by_user_id": "user-test",
                    "started_by_role": "future-role",
                    "started_at": 10,
                    "recorded": False,
                    "participants": [{"user_id": "user-test", "role": "future-role"}],
                }
            ]
        },
        ("home-test", "visit-test"),
    ),
    ReadCase(
        "vendor_visit_conversation",
        f"{H}/vendor_visits/visit-test/conversation",
        VisitConversation,
        CONVERSATION,
        ("home-test", "visit-test"),
    ),
    ReadCase(
        "vendor_visit_purchases",
        f"{H}/vendor_visits/visit-test/purchases",
        ScopedPurchasesResponse,
        SCOPED_PURCHASES,
        ("home-test", "visit-test"),
    ),
    ReadCase(
        "help_center_bundle",
        "/protected/help_center/app-test/bundle",
        HelpCenterBundleResponse,
        {
            "data": {
                "app": "future-app",
                "topics": [
                    {
                        "id": "topic-test",
                        "slug": "example",
                        "name": "Example topic",
                        "blurb": "Example blurb",
                        "systemImage": "x",
                        "sortOrder": 1,
                    }
                ],
                "articles": [
                    {
                        "id": "article-test",
                        "topicId": "topic-test",
                        "slug": "example",
                        "sortOrder": 1,
                        "isTopQuestion": False,
                        "isFeatured": False,
                        "articleVersionId": "version-test",
                        "versionNumber": 1,
                        "title": "Example article",
                        "summary": "Example summary",
                        "bodyMarkdown": "Example body",
                    }
                ],
            }
        },
        ("app-test",),
    ),
    ReadCase(
        "referral_code",
        "/protected/member/referral_code/v2",
        ReferralCodeResponse,
        {
            "referral_code": {
                "code": "EXAMPLE",
                "referral_url": "https://example.invalid/referral",
                "display": {"synthetic_label": "Example label", "synthetic_nested": OPAQUE},
                "referred_homes": [OPAQUE],
            }
        },
        (),
    ),
]

# Reads confirmed in live traffic. Everything else in CASES is static-only.
VERIFIED_READS = frozenset(
    {
        "bookable_handyman_tasks",
        "inventory_enums",
        "inventory_paint_matches",
        "help_center_bundle",
        "referral_code",
        "release_notes_diff",
        "home_feed",
    }
)


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


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Static read tests must never open a socket")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_named_typed_get_contract(case: ReadCase) -> None:
    api, client = make_api(case.payload)
    method = getattr(api, case.name)
    assert inspect.iscoroutinefunction(method)
    assert get_type_hints(method)["return"] is case.model
    result = await method(*case.args)
    assert type(result) is case.model
    assert client.calls == [(case.path, case.params)]  # No helpers, writes or URL fetches.
    verified = case.name in VERIFIED_READS
    assert is_unverified(method) is not verified
    doc = method.__doc__ or ""
    assert doc.startswith("VERIFIED" if verified else "UNVERIFIED")
    if verified:
        assert "2026-10" in doc


@pytest.mark.parametrize(
    ("name", "evidence"),
    [
        ("membership_info", "404"),
        ("membership_savings", "MEMBERSHIP_SAVINGS_NOT_FOUND"),
    ],
)
def test_non_200_probe_results_recorded_without_promotion(name: str, evidence: str) -> None:
    method = getattr(CasaApi, name)
    assert is_unverified(method)
    doc = method.__doc__ or ""
    assert "2026-10" in doc
    assert evidence in doc


async def test_referral_code_keeps_unverified_shapes_opaque() -> None:
    case = next(case for case in CASES if case.name == "referral_code")
    api, _ = make_api(case.payload)
    result = await api.referral_code()
    assert result.referral_code.display["synthetic_nested"] == OPAQUE
    assert result.referral_code.referred_homes == [OPAQUE]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_malformed_envelope_is_sanitized_not_raw_fallback(case: ReadCase) -> None:
    api, _ = make_api({"error": CANARY})
    with pytest.raises(CasaResponseError, match="validation error") as error:
        await getattr(api, case.name)(*case.args)
    assert CANARY not in str(error.value)
    assert CANARY not in repr(error.value)
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_unknown_fields_retained_at_every_typed_level(case: ReadCase) -> None:
    def add_extra(value: Any) -> None:
        if isinstance(value, dict):
            for child in list(value.values()):
                add_extra(child)
            value["synthetic_future_extra"] = "retained"
        elif isinstance(value, list):
            for child in value:
                add_extra(child)

    payload = deepcopy(case.payload)
    add_extra(payload)
    api, _ = make_api(payload)
    model = await getattr(api, case.name)(*case.args)

    def check(value: Any) -> None:
        if isinstance(value, BaseModel):
            assert value.model_extra is not None
            assert value.model_extra["synthetic_future_extra"] == "retained"
            for name in type(value).model_fields:
                check(getattr(value, name))
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(model)


BAD_IDS = [
    "",
    ".",
    "..",
    "/",
    "a/b",
    "a\\b",
    "a?b",
    "a#b",
    "%2f",
    "%252f",
    "../other",
    "https://example.invalid",
    "a b",
    "a\n",
    "a\x00",
    "a\x7f",
    "a\x85",
    "a" * 2049,
    True,
    None,
    1.5,
]
ID_CASES = [(case, index) for case in CASES for index in range(len(case.args))]


@pytest.mark.parametrize(
    ("case", "index"), ID_CASES, ids=[f"{case.name}:{index}" for case, index in ID_CASES]
)
@pytest.mark.parametrize("bad_id", BAD_IDS)
async def test_every_path_identifier_rejected_before_io(
    case: ReadCase, index: int, bad_id: Any
) -> None:
    api, client = make_api(case.payload)
    args: list[Any] = list(case.args)
    args[index] = bad_id
    with pytest.raises(ValueError, match="identifier") as error:
        await getattr(api, case.name)(*args)
    assert not client.calls
    if isinstance(bad_id, str) and bad_id:
        assert bad_id not in str(error.value)


@pytest.mark.parametrize("bad_id", [value for value in BAD_IDS if value is not None])
async def test_bookable_query_identifier_validation(bad_id: Any) -> None:
    api, client = make_api({"items": []})
    with pytest.raises(ValueError, match="identifier"):
        await api.bookable_handyman_tasks("home-test", include_current_vendor_visit_id=bad_id)
    assert not client.calls


async def test_bookable_optional_query_preserved_and_items_not_discriminated() -> None:
    api, client = make_api({"items": [OPAQUE], "total_additional_availability_minutes": None})
    result = await api.bookable_handyman_tasks(
        "home-test", include_current_vendor_visit_id="Visit.001~test"
    )
    assert result.items == [OPAQUE]
    assert result.total_additional_availability_minutes is None
    assert client.calls == [
        (
            f"{H}/vendor_visits/handyman/bookable_tasks",
            {"include_current_vendor_visit_id": "Visit.001~test"},
        )
    ]


async def test_opaque_visit_unions_and_future_statuses_preserved() -> None:
    api, client = make_api(VISIT)
    visit = await api.vendor_visit_details("home-test", "visit-test")
    assert visit.task_items == [OPAQUE]
    assert visit.feedback == OPAQUE
    assert visit.request.type == "future-type"
    client.payload = CONVERSATION
    conversation = await api.vendor_visit_conversation("home-test", "visit-test")
    assert conversation.messages[0].parts == [OPAQUE]
    assert conversation.messages[0].sender_role == "future-role"
    assert conversation.event_cursor == "synthetic/opaque+=?"
    assert len(client.calls) == 2


async def test_release_diff_sends_current_build() -> None:
    api, client = make_api({"data": []})
    assert (await api.release_notes_diff(current_build=700)).data == []
    assert client.calls == [("/protected/release_notes/member_ios/diff", {"currentBuild": "700"})]
    assert "400" in (api.release_notes_diff.__doc__ or "")


async def test_home_feed_sends_app_build_and_keeps_props_opaque() -> None:
    case = next(case for case in CASES if case.name == "home_feed")
    api, client = make_api(case.payload)
    feed = await api.home_feed("home-test", app_build=2_147_483_647)
    assert client.calls == [(f"{H}/feed", {"app_build": "2147483647"})]
    assert feed.cards[0].props["visual_style"] == OPAQUE
    assert feed.cards[0].children == []
    assert "INVALID_INPUT_PARAMETERS" in (api.home_feed.__doc__ or "")


async def test_home_feed_parses_nested_children() -> None:
    card: dict[str, Any] = {
        "id": "child-test",
        "template_id": "t",
        "name": "Child",
        "props": {},
        "show_starts_at_minutes_after_onboarding": 5,
        "show_ends_at_minutes_after_onboarding": 10,
        "children": [],
    }
    parent = {**card, "id": "parent-test", "children": [card]}
    api, _ = make_api({"cards": [parent]})
    feed = await api.home_feed("home-test")
    assert feed.cards[0].children[0].show_ends_at_minutes_after_onboarding == 10


@pytest.mark.parametrize("bad", [0, -1, 2_147_483_648, True, "698", 6.98, None])
@pytest.mark.parametrize("name", ["home_feed", "release_notes_diff"])
async def test_build_numbers_validated_before_io(name: str, bad: Any) -> None:
    api, client = make_api({"data": [], "cards": []})
    with pytest.raises(ValueError):
        if name == "home_feed":
            await api.home_feed("home-test", app_build=bad)
        else:
            await api.release_notes_diff(current_build=bad)
    assert client.calls == []


@pytest.mark.parametrize(
    "value", ["001", "Mixed.Case~test", "light_fixture_type", "home_type", "a" * 2048]
)
async def test_identifiers_preserved_and_limit_inclusive(value: str) -> None:
    api, client = make_api({"enums": []})
    await api.inventory_enums(value)
    assert client.calls == [(f"/protected/member/inventory/enums/enum_type/{value}", {})]


@pytest.mark.parametrize("name", [case.name for case in CASES])
async def test_known_nested_fields_reject_canary_without_leaking(name: str) -> None:
    case = next(case for case in CASES if case.name == name)
    payload = deepcopy(case.payload)
    match name:
        case "bookable_handyman_tasks":
            payload["total_additional_availability_minutes"] = CANARY
        case "membership_info":
            payload["benefits"][0]["title"] = {"secret": CANARY}
        case "membership_savings":
            payload["summary"]["total_money_saved_cents"] = CANARY
        case "inventory_enums":
            payload["enums"][0]["name"] = {"secret": CANARY}
        case "release_notes_diff":
            payload["data"][0]["date"] = {"secret": CANARY}
        case "home_feed":
            payload["cards"][0]["show_starts_at_minutes_after_onboarding"] = CANARY
        case "availability_request_details":
            payload["slots"][0]["start_time"] = CANARY
        case "document_details":
            payload["document"]["size_bytes"] = CANARY
        case "document_suggestions":
            payload["suggestions"][0]["citations"][0]["page_index"] = CANARY
        case "document_structure_suggestions":
            payload["suggestions"][0]["changed_since_analysis"] = CANARY
        case "inventory_paint_matches":
            payload["matches"][0]["closeness_percentage"] = CANARY
        case "request_purchases" | "vendor_visit_purchases":
            payload["purchased_items"][0]["quantity"] = CANARY
        case "task_details":
            payload["updates"][0]["sent_at"] = CANARY
        case "vendor_visit_details":
            payload["calendar_event"]["start_time"] = CANARY
        case "vendor_visit_autopilot_plan":
            payload["tasks"][0]["updates"][0]["sent_at"] = CANARY
        case "vendor_visit_calls":
            payload["calls"][0]["participants"][0]["joined_at"] = CANARY
        case "vendor_visit_conversation":
            payload["messages"][0]["created_at"] = CANARY
        case "help_center_bundle":
            payload["data"]["topics"][0]["sortOrder"] = CANARY
        case "referral_code":
            payload["referral_code"]["code"] = {"secret": CANARY}
    api, _ = make_api(payload)
    with pytest.raises(CasaResponseError) as error:
        await getattr(api, name)(*case.args)
    assert CANARY not in str(error.value)
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(error.value))


def test_no_fabricated_purchase_union_or_call_grant_models() -> None:
    assert not hasattr(CasaApi, "purchase_details")
    assert not hasattr(CasaApi, "vendor_visit_call_grant")
    assert "token" not in VisitCallsResponse.model_fields
    assert "room_url" not in VisitCallsResponse.model_fields
