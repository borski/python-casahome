"""Offline-only synthetic transport coverage for reconstructed contracts."""

from __future__ import annotations

import json
import traceback
from copy import deepcopy
from typing import Any, cast

import pytest
from pydantic import ValidationError

from casahome import CasaApi, CasaAuthError, CasaRequestError, CasaResponseError
from casahome._common import is_unverified
from casahome.models import (
    SupportRequestBody,
    UpdateRequestDetailBody,
    UpdateRoomPropertiesBody,
    UpdateRoomProperty,
    UpdateStoryBody,
    UpdateTaskResponse,
    UpdateTaskScalarBody,
)
from casahome.models.documents import DocumentStructureSuggestion, HomeDocument
from casahome.models.home import HomeStory
from casahome.models.tasks import TaskDetails
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer

RID = "synthetic-id"
HOME = f"/protected/home/{HOME_ID}"
MEMBER = f"/protected/member/home/{HOME_ID}"
CANARY = "private-synthetic-canary"
TASK_RESPONSE: dict[str, Any] = {
    "id": RID,
    "title": "Example",
    "description": "Example",
    "emoji": "!",
    "status": "future",
    "updates": [],
    "can_schedule_handyman_vendor_visit": False,
    "can_chat_with_concierge": False,
    "can_edit": False,
    "can_delete": False,
}
CAPABILITY_FIELDS = (
    "can_schedule_handyman_vendor_visit",
    "can_chat_with_concierge",
    "can_edit",
    "can_delete",
)


@pytest.mark.parametrize("bad", ["false", 0, 1, None])
def test_structure_changed_flag_is_strict(bad: object) -> None:
    payload = {
        "id": RID,
        "section": "inventory",
        "title": "Example",
        "current_values": [],
        "current_label": "Old",
        "proposed_label": "New",
        "reason": "Example",
        "state": "pending",
        "citations": [],
        "changed_since_analysis": bad,
    }
    with pytest.raises(ValidationError):
        DocumentStructureSuggestion.model_validate(payload)
    payload["changed_since_analysis"] = False
    assert DocumentStructureSuggestion.model_validate(payload).changed_since_analysis is False


@pytest.mark.parametrize("bad", ["0", False, True, 0.0, None])
def test_story_floor_is_strict(bad: object) -> None:
    with pytest.raises(ValidationError):
        HomeStory.model_validate({"id": RID, "name": "Ground", "floor_number": bad})
    story = HomeStory.model_validate({"id": RID, "name": "Ground", "floor_number": 0})
    assert story.floor_number == 0


@pytest.mark.parametrize("bad", ["42", True, -1.2])
def test_document_size_rejects_coercion(bad: object) -> None:
    with pytest.raises(ValidationError):
        HomeDocument.model_validate({"id": RID, "name": "Example", "size_bytes": bad})
    document = HomeDocument.model_validate({"id": RID, "name": "Example", "size_bytes": 0})
    assert document.size_bytes == 0


@pytest.mark.parametrize(
    ("name", "method", "route", "args", "response", "body"),
    [
        (
            "update_request_detail",
            "PATCH",
            f"{HOME}/requests/{RID}",
            (UpdateRequestDetailBody(read_state="unread"),),
            {
                "id": RID,
                "type": "future_type",
                "status": "future_status",
                "title": "Example",
                "emoji": "*",
                "has_unread_messages": False,
            },
            {"read_state": "unread"},
        ),
        (
            "dismiss_document_structure_suggestion",
            "POST",
            f"{HOME}/documents/{RID}/structure_suggestions/{RID}/respond",
            (RID, RID, ["first", "second"]),
            {"saved": False},
            {"decision": "dismissed", "expected_values": ["first", "second"]},
        ),
        (
            "update_task",
            "PATCH",
            f"{HOME}/tasks/{RID}",
            (UpdateTaskScalarBody(emoji="!"),),
            {
                "id": RID,
                "title": "Example",
                "description": "Example",
                "emoji": "!",
                "status": "future",
                "updates": [],
                "can_schedule_handyman_vendor_visit": False,
                "can_chat_with_concierge": False,
                "can_edit": False,
                "can_delete": False,
            },
            {"emoji": "!"},
        ),
        ("delete_task", "DELETE", f"{HOME}/tasks/{RID}", (), {"message": "pending"}, None),
        (
            "transfer_task_to_concierge",
            "POST",
            f"{HOME}/tasks/{RID}/transfer_to_concierge",
            (),
            {"request_id": RID, "title": "Example", "message": "pending"},
            None,
        ),
        ("delete_document", "DELETE", f"{HOME}/documents/{RID}", (), {"deleted": False}, None),
        (
            "update_room_properties",
            "PATCH",
            f"{MEMBER}/room/{RID}/props",
            (UpdateRoomPropertiesBody(props=[UpdateRoomProperty(definition_id=RID, value="")]),),
            {"message": "pending"},
            {"props": [{"definition_id": RID, "value": ""}]},
        ),
        (
            "update_story",
            "PATCH",
            f"{MEMBER}/story/{RID}",
            (UpdateStoryBody(floor_number=0),),
            {"message": "pending"},
            {"floor_number": 0},
        ),
        (
            "retailer_discounts",
            "GET",
            f"{HOME}/retailer_discounts",
            (),
            {
                "data": [
                    {
                        "id": RID,
                        "vendor_id": RID,
                        "retailer_name": "Example",
                        "discount_headline": "Example",
                        "sort_order": 0,
                        "future": [1],
                    }
                ]
            },
            None,
        ),
        (
            "create_support_request",
            "POST",
            f"{HOME}/support_requests",
            (SupportRequestBody(content="Example"),),
            {"request_id": RID},
            {"content": "Example"},
        ),
        (
            "mark_vendor_visit_conversation_read",
            "PATCH",
            f"{HOME}/vendor_visits/{RID}/conversation/read",
            (),
            {"ok": False},
            None,
        ),
    ],
)
async def test_recovered_transport(
    api: CasaApi,
    server: FakeServer,
    token_ok: None,
    name: str,
    method: str,
    route: str,
    args: tuple[Any, ...],
    response: dict[str, Any],
    body: dict[str, Any] | None,
) -> None:
    assert is_unverified(getattr(api, name))
    server.add(method, route, payload={**response, "future_response": "preserved"})
    if name in {
        "dismiss_document_structure_suggestion",
        "retailer_discounts",
        "create_support_request",
    }:
        result = await getattr(api, name)(HOME_ID, *args)
    else:
        result = await getattr(api, name)(HOME_ID, RID, *args)
    assert result.model_extra == {"future_response": "preserved"}
    if name == "retailer_discounts":
        assert result.data[0].model_extra == {"future": [1]}
    if name == "update_task":
        assert isinstance(result, UpdateTaskResponse)
        assert all(getattr(result, field) is False for field in CAPABILITY_FIELDS)
    false_fields = {
        "delete_document": "deleted",
        "mark_vendor_visit_conversation_read": "ok",
        "dismiss_document_structure_suggestion": "saved",
    }
    if name in false_fields:
        assert getattr(result, false_fields[name]) is False
    (call,) = server.calls(method, route)
    assert (json.loads(call.body) if call.body else None) == body
    if method != "GET":
        assert len(server.calls("POST", TOKEN_PATH)) == 1


@pytest.mark.parametrize(
    ("name", "route", "response"),
    [
        ("delete_document", f"{HOME}/documents/{RID}", {}),
        ("delete_document", f"{HOME}/documents/{RID}", {"deleted": "true"}),
        (
            "mark_vendor_visit_conversation_read",
            f"{HOME}/vendor_visits/{RID}/conversation/read",
            {},
        ),
    ],
)
async def test_invalid_write_result_is_unknown_not_retried(
    api: CasaApi,
    server: FakeServer,
    token_ok: None,
    name: str,
    route: str,
    response: dict[str, Any],
) -> None:
    method = "DELETE" if name == "delete_document" else "PATCH"
    server.add(method, route, payload=response)
    with pytest.raises(CasaResponseError) as caught:
        await getattr(api, name)(HOME_ID, RID)
    assert caught.value.__context__ is None
    assert len(server.calls(method, route)) == 1


@pytest.mark.parametrize(
    ("name", "body"),
    [
        (
            "update_request_detail",
            UpdateRequestDetailBody.model_construct(title=None, read_state=None),
        ),
        (
            "update_task",
            UpdateTaskScalarBody.model_construct(title=None, description=None, emoji=None),
        ),
        ("update_story", UpdateStoryBody.model_construct(name=None, floor_number=None)),
        (
            "update_room_properties",
            UpdateRoomPropertiesBody.model_construct(
                props=[cast(Any, {"definition_id": RID, "value": {"secret": CANARY}})]
            ),
        ),
    ],
)
async def test_invalid_body_no_io_and_scrubbed(
    api: CasaApi,
    server: FakeServer,
    name: str,
    body: Any,
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await getattr(api, name)(HOME_ID, RID, body)
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert not server.seen


async def test_write_401_one_attempt(api: CasaApi, server: FakeServer, token_ok: None) -> None:
    path = f"{HOME}/documents/{RID}"
    server.add("DELETE", path, status=401, body="rejected")
    with pytest.raises(CasaAuthError):
        await api.delete_document(HOME_ID, RID)
    assert len(server.calls("DELETE", path)) == 1


@pytest.mark.parametrize("field", CAPABILITY_FIELDS)
@pytest.mark.parametrize("bad", [1, 0, "true", "false", None, "missing"])
async def test_task_patch_capabilities_strict_after_write(
    api: CasaApi, server: FakeServer, token_ok: None, field: str, bad: Any
) -> None:
    path = f"{HOME}/tasks/{RID}"
    response = deepcopy(TASK_RESPONSE)
    if bad == "missing":
        del response[field]
    else:
        response[field] = bad
    response["future_response"] = {"synthetic": CANARY}
    server.add("PATCH", path, payload=response)
    with pytest.raises(CasaResponseError) as caught:
        await api.update_task(HOME_ID, RID, UpdateTaskScalarBody(emoji="!"))
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert len(server.calls("PATCH", path)) == 1
    assert len(server.calls("POST", TOKEN_PATH)) == 1


def test_legacy_task_get_capability_coercion_unchanged() -> None:
    response = {**TASK_RESPONSE, "can_edit": 1, "can_delete": "false"}
    legacy = TaskDetails.model_validate(response)
    assert legacy.can_edit is True
    assert legacy.can_delete is False


async def test_task_patch_preserves_true_and_extra(
    api: CasaApi, server: FakeServer, token_ok: None
) -> None:
    path = f"{HOME}/tasks/{RID}"
    response = {**TASK_RESPONSE, **dict.fromkeys(CAPABILITY_FIELDS, True)}
    server.add("PATCH", path, payload={**response, "future_response": [1, None]})
    result = await api.update_task(HOME_ID, RID, UpdateTaskScalarBody(title="Example"))
    assert isinstance(result, UpdateTaskResponse)
    assert all(getattr(result, field) is True for field in CAPABILITY_FIELDS)
    assert result.model_extra == {"future_response": [1, None]}
    assert len(server.calls("PATCH", path)) == 1


async def test_task_patch_401_one_attempt(api: CasaApi, server: FakeServer, token_ok: None) -> None:
    path = f"{HOME}/tasks/{RID}"
    server.add("PATCH", path, status=401, body="rejected")
    with pytest.raises(CasaAuthError):
        await api.update_task(HOME_ID, RID, UpdateTaskScalarBody(emoji="!"))
    assert len(server.calls("PATCH", path)) == 1
