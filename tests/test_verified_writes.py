"""Live-verified writes and read upgrades, exercised against the loopback FakeServer.

All data is synthetic. Network access is restricted to loopback, so the
Cloud Storage step targets the FakeServer through a patched storage origin.
"""

from __future__ import annotations

import inspect
import ipaddress
import json
import socket
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import JsonValue
from yarl import URL

from casahome import (
    CasaApi,
    CasaApiError,
    CasaAuthError,
    CasaConnectionError,
    CasaRequestError,
    CasaResponseError,
    SentCasaAIMessage,
    is_unverified,
    uploads,
)
from casahome.models import (
    AI_PART_DATA_TODO,
    AI_PART_TEXT,
    CasaAIMessageUpsertChange,
    CasaAIThreadUpdate,
    CasaAIUnknownChange,
    DocumentUploadFile,
    MultiSelectAnswer,
    MultiSelectRoundAnswer,
    NotificationSettingUpdate,
    RequestSummary,
    SingleSelectAnswer,
    SingleSelectRoundAnswer,
    TodoReadDetail,
)
from casahome.streaming import CasaAIThreadUpdateEvent
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer

H = f"/protected/home/{HOME_ID}"
MH = f"/protected/member/home/{HOME_ID}"
CANARY = "SYNTHETIC-PRIVATE-INPUT-NOT-A-CREDENTIAL"
STORAGE_PATH = "/upload/storage/v1/b/example-bucket/o"
TOKEN = {
    "access_token": "synthetic-access",
    "expires_in": "3600",
    "token_type": "Bearer",
    "refresh_token": "synthetic-refresh",
    "id_token": "synthetic-id",
    "user_id": "synthetic-user",
    "project_id": "synthetic-project",
}
TODO: dict[str, Any] = {
    "id": "todo-1",
    "title": "Example task",
    "emoji": "x",
    "original_text": "Example input",
    "prepared_brief": "Example brief",
    "status": "materialized",
    "creator_role": "member",
    "is_suggested": False,
    "flagged_for_support": False,
    "attachments": [],
    "question_rounds": [
        {
            "id": "round-1",
            "sequence": 1,
            "state": "answered",
            "questions": [{"id": "question-1", "future": True}],
        }
    ],
    "destination": {"kind": "request", "id": "request-1"},
    "can_delete": False,
    "created_at": 10,
    "updated_at": 11,
}
AI_MESSAGE: dict[str, Any] = {
    "id": "message-1",
    "content": "Example question",
    "sender_role": "member",
    "created_at": 20,
    "feedback": None,
    "parts": [{"type": "text", "id": "part-1", "text": "Example question"}],
    "attachments": [],
}
DOCUMENT: dict[str, Any] = {
    "id": "document-1",
    "home_id": HOME_ID,
    "original_filename": "example.pdf",
    "name": "Example document",
    "document_type": "other",
    "document_date": None,
    "mimetype": "application/pdf",
    "size_bytes": 18,
    "uploaded_by_name": "Example Person",
    "created_at": 30,
    "updated_at": 31,
    "organization": {
        "id": "org-1",
        "status": "queued",
        "error_code": None,
        "can_retry": False,
        "completed_at": None,
    },
    "extraction": {
        "id": "ext-1",
        "status": "queued",
        "error_code": None,
        "can_retry": False,
        "completed_at": None,
        "pending_count": 0,
        "pending_structure_count": 0,
        "accepted_count": 0,
        "dismissed_count": 0,
        "already_handled_count": 0,
    },
}
DOCUMENT_TYPES: dict[str, Any] = {
    "types": [{"key": "other", "label": "Other", "description": "Example"}],
    "max_file_size_bytes": 64,
    "max_files_per_upload": 5,
    "allowed_mimetypes": ["application/pdf", "image/png"],
}
NOTIFICATION_GROUPS: dict[str, Any] = {
    "groups": [
        {
            "key": "general",
            "display_name": "General",
            "sort_order": 0,
            "types": [
                {
                    "key": "example_type",
                    "display_name": "Example",
                    "description": "Example",
                    "sort_order": 0,
                    "channels": [
                        {
                            "channel": "push",
                            "enabled": False,
                            "default_enabled": True,
                            "required": False,
                        }
                    ],
                }
            ],
        }
    ]
}
MAILBOX: dict[str, Any] = {
    "id": "mailbox-1",
    "status": "active",
    "onboarding_status": "pending",
    "address": {"line1": "1 Example St", "city": "Example", "state": "EX", "postal_code": "00000"},
    "quota": {"month": "2026-10", "used": 0, "included": 10, "overage_rate_usd_cents": 100},
    "claimed_at": "2026-10-01T00:00:00Z",
}


@dataclass
class WriteCase:
    name: str
    call: Callable[[CasaApi], Awaitable[Any]]
    method: str
    path: str
    body: Any  # Exact decoded JSON, or None for no body.
    status: int = 200
    response: Any = None
    check: Callable[[Any], bool | None] = lambda _: None
    headers: dict[str, str] = field(default_factory=dict)


def _check_todo(result: Any) -> None:
    assert isinstance(result.todo, TodoReadDetail)
    assert result.todo.destination is not None
    assert result.todo.destination.kind == "request"
    assert result.todo.question_rounds[0].state == "answered"


CASES = [
    WriteCase(
        "move_entity_to_room",
        lambda api: api.move_entity_to_room(HOME_ID, "entity-1", "room-2"),
        "POST",
        f"{MH}/entity/entity-1/room/room-2",
        None,
        response={"message": "ok"},
        check=lambda r: r.message == "ok",
    ),
    WriteCase(
        "rename_room",
        lambda api: api.rename_room(HOME_ID, "room-1", room_type_id="type-1", name="Example room"),
        "PATCH",
        f"{MH}/room/room-1",
        {"room_type_id": "type-1", "name": "Example room"},
        response={"message": "Room updated"},
        check=lambda r: r.message == "Room updated",
    ),
    WriteCase(
        "update_entity_make_model",
        lambda api: api.update_entity_make_model(
            HOME_ID, "entity-1", make_id="make-1", model_name="Example model"
        ),
        "POST",
        f"{MH}/entity/entity-1/save_and_publish",
        {"make": {"id": "make-1"}, "model": {"name": "Example model"}, "props": []},
        response={
            "entity_id": "entity-1",
            "status": "published",
            "make": {"id": "make-1", "name": "Example make"},
            "model": {"id": "model-1", "name": "Example model"},
            "identity": {
                "state": "verified",
                "unverified_make": None,
                "unverified_model": None,
                "candidates": [],
            },
        },
        check=lambda r: r.identity.state == "verified" and r.model.id == "model-1",
    ),
    WriteCase(
        "send_ai_message",
        lambda api: api.send_ai_message(
            HOME_ID, "Example question", upload_ids=["upload-1"], idempotency_key="key-1"
        ),
        "POST",
        f"{H}/casa_ai/messages",
        {"input": {"type": "message", "text": "Example question", "upload_ids": ["upload-1"]}},
        status=202,
        response={
            "member_message": AI_MESSAGE,
            "active_response": {
                "message_id": "message-2",
                "status_message": "Working",
                "parts": [],
            },
        },
        headers={"Idempotency-Key": "key-1"},
    ),
    WriteCase(
        "rate_ai_message",
        lambda api: api.rate_ai_message(HOME_ID, "message-2", "good"),
        "PUT",
        f"{H}/casa_ai/messages/message-2/feedback",
        {"rating": "good"},
        response={"success": True, "feedback": {"rating": "good"}},
    ),
    WriteCase(
        "clear_ai_message_rating",
        lambda api: api.clear_ai_message_rating(HOME_ID, "message-2"),
        "DELETE",
        f"{H}/casa_ai/messages/message-2/feedback",
        None,
        status=204,
    ),
    WriteCase(
        "answer_todo_question",
        lambda api: api.answer_todo_question(
            HOME_ID,
            "todo-1",
            "round-1",
            "question-1",
            answer=SingleSelectAnswer(selected_option_index=0),
        ),
        "PUT",
        f"{H}/todos/todo-1/question_rounds/round-1/questions/question-1/answer",
        {
            "is_skipped": False,
            "answer": {"kind": "single_select", "other_text": None, "selected_option_index": 0},
        },
        status=204,
    ),
    WriteCase(
        "submit_todo_question_round",
        lambda api: api.submit_todo_question_round(
            HOME_ID,
            "todo-1",
            "round-1",
            [
                SingleSelectRoundAnswer(question_id="question-1", selected_option_index=1),
                MultiSelectRoundAnswer(
                    question_id="question-2", selected_option_indexes=[0, 2], other_text="Other"
                ),
            ],
        ),
        "POST",
        f"{H}/todos/todo-1/question_rounds/round-1/answers",
        {
            "answers": [
                {
                    "question_id": "question-1",
                    "input_kind": "single_select",
                    "selected_option_index": 1,
                    "other_text": None,
                },
                {
                    "question_id": "question-2",
                    "input_kind": "multi_select",
                    "selected_option_indexes": [0, 2],
                    "other_text": "Other",
                },
            ]
        },
        status=202,
        response={"todo": TODO},
        check=_check_todo,
    ),
    WriteCase(
        "respond_to_suggested_todo",
        lambda api: api.respond_to_suggested_todo(HOME_ID, "suggestion-1", "accept"),
        "POST",
        f"{H}/suggested_todos/suggestion-1/respond",
        {"decision": "accept"},
        status=202,
        response={"todo": TODO},
        check=_check_todo,
    ),
    WriteCase(
        "send_todo_to_concierge",
        lambda api: api.send_todo_to_concierge(HOME_ID, "todo-1"),
        "POST",
        f"{H}/todos/todo-1/materialize",
        {"destination": "concierge"},
        status=201,
        response={"todo": TODO},
        check=_check_todo,
    ),
    WriteCase(
        "materialize_todo",
        lambda api: api.materialize_todo(HOME_ID, "todo-1"),
        "POST",
        f"{H}/todos/todo-1/materialize",
        {"destination": "concierge"},
        status=201,
        response={"todo": TODO},
        check=_check_todo,
    ),
    WriteCase(
        "update_autopilot_plan",
        lambda api: api.update_autopilot_plan(
            HOME_ID,
            "plan-1",
            enabled=True,
            selected_cadence="every_quarter",
            next_desired_occurrence_date=date(2026, 11, 2),
        ),
        "PATCH",
        f"{H}/autopilot/plan-1",
        {
            "next_desired_occurrence_date": "2026-11-02",
            "selected_cadence": "every_quarter",
            "associations_enabled_map": {},
            "enabled": True,
        },
        response={"message": "ok"},
    ),
    WriteCase(
        "update_notification_settings",
        lambda api: api.update_notification_settings(
            HOME_ID,
            [
                NotificationSettingUpdate(
                    notification_type="example_type", channel="push", enabled=False
                )
            ],
        ),
        "PUT",
        f"{H}/notification_settings",
        {"settings": [{"notification_type": "example_type", "channel": "push", "enabled": False}]},
        response=NOTIFICATION_GROUPS,
        check=lambda r: r.groups[0].types[0].channels[0].enabled is False,
    ),
    WriteCase(
        "update_access_preferences",
        lambda api: api.update_access_preferences(
            HOME_ID,
            general_instructions=None,
            package_pickup_method="pickup_spot",
            package_pickup_spot="other",
            package_pickup_general_instructions="Example note",
        ),
        "PATCH",
        f"{H}/access_preferences",
        {
            "general_instructions": None,
            "package_pickup_method": "pickup_spot",
            "package_pickup_spot": "other",
            "package_pickup_general_instructions": "Example note",
        },
        response={
            "home_id": HOME_ID,
            "general_instructions": None,
            "package_pickup_method": "pickup_spot",
            "package_pickup_spot": "other",
            "package_pickup_general_instructions": "Example note",
        },
        check=lambda r: r.package_pickup_spot == "other",
    ),
    WriteCase(
        "claim_mailbox",
        lambda api: api.claim_mailbox(HOME_ID),
        "POST",
        f"{H}/mailbox/claim",
        None,
        response={"mailbox": MAILBOX},
        check=lambda r: r.mailbox.id == "mailbox-1",
    ),
    WriteCase(
        "create_document_upload_sessions",
        lambda api: api.create_document_upload_sessions(
            HOME_ID, [DocumentUploadFile(size_bytes=18, mimetype="application/pdf")]
        ),
        "POST",
        f"{H}/documents/sessions",
        {"files": [{"size_bytes": 18, "mimetype": "application/pdf"}]},
        response={
            "uploads": [{"upload_id": "upload-1", "session_url": "https://example.invalid/x"}]
        },
        check=lambda r: r.uploads[0].upload_id == "upload-1",
    ),
    WriteCase(
        "create_document",
        lambda api: api.create_document(HOME_ID, "upload-1", "example.pdf", find_todos=False),
        "POST",
        f"{H}/documents",
        {"find_todos": False, "upload_id": "upload-1", "original_filename": "example.pdf"},
        status=201,
        response={"document": DOCUMENT, "already_exists": False},
        check=lambda r: r.document.extraction.pending_count == 0,
    ),
]
VERIFIED_WRITES = sorted(
    {case.name for case in CASES} - {"clear_ai_message_rating"}
    | {"upload_document_content", "upload_document"}
)


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else address
        try:
            allowed = ipaddress.ip_address(host).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise AssertionError("Write tests forbid non-loopback network access")
        connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture(autouse=True)
def synthetic_token(server: FakeServer) -> None:
    server.add("POST", TOKEN_PATH, payload=TOKEN)


@pytest.fixture
def storage(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the storage origin check at the FakeServer and return a session URL."""
    origin = URL(server.url)
    monkeypatch.setattr(uploads, "STORAGE_UPLOAD_SCHEME", origin.scheme)
    monkeypatch.setattr(uploads, "STORAGE_UPLOAD_HOST", origin.host)
    monkeypatch.setattr(uploads, "STORAGE_UPLOAD_PORT", origin.port)
    return f"{server.url}{STORAGE_PATH}?uploadType=resumable&upload_id=synthetic-session"


def _respond(server: FakeServer, case: WriteCase) -> None:
    if case.response is None:
        server.add(case.method, case.path, status=case.status)
    else:
        server.add(case.method, case.path, status=case.status, payload=case.response)


# Contracts -----------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_write_wire_contract(api: CasaApi, server: FakeServer, case: WriteCase) -> None:
    _respond(server, case)
    result = await case.call(api)
    (call,) = server.calls(case.method, case.path)
    if case.body is None:
        assert call.body == ""
        assert call.headers.get("Content-Type") != "application/json"
    else:
        assert json.loads(call.body) == case.body
        assert call.headers["Content-Type"] == "application/json"
    for name, value in case.headers.items():
        assert call.headers[name] == value
    if case.name != "send_ai_message":
        assert "Idempotency-Key" not in call.headers
    assert call.headers["Authorization"] == "Bearer synthetic-id"
    if case.status == 204:
        assert result is None
    else:
        assert case.check(result) is not False


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_writes_never_retry_on_401(api: CasaApi, server: FakeServer, case: WriteCase) -> None:
    server.add(case.method, case.path, status=401, payload={"error": "synthetic_expired"})
    server.add(case.method, case.path, status=case.status, payload=case.response)
    with pytest.raises(CasaAuthError):
        await case.call(api)
    assert len(server.calls(case.method, case.path)) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_write_errors_drop_raw_body(
    api: CasaApi, server: FakeServer, case: WriteCase
) -> None:
    server.add(case.method, case.path, status=500, body=f"<html>{CANARY}</html>")
    with pytest.raises(CasaApiError) as caught:
        await case.call(api)
    assert CANARY not in str(caught.value)
    assert len(server.calls(case.method, case.path)) == 1


@pytest.mark.parametrize("name", VERIFIED_WRITES)
def test_verified_writes_document_evidence(name: str) -> None:
    method = getattr(CasaApi, name)
    assert inspect.iscoroutinefunction(method)
    assert not is_unverified(method)
    doc = method.__doc__ or ""
    assert doc.startswith("VERIFIED (live, 2026-10)")


def test_clear_rating_stays_unverified() -> None:
    assert is_unverified(CasaApi.clear_ai_message_rating)
    assert (CasaApi.clear_ai_message_rating.__doc__ or "").startswith("UNVERIFIED")


def test_still_unverified_writes_unchanged() -> None:
    assert is_unverified(CasaApi.update_entity_properties)
    for name in ("create_todo", "create_todo_result", "send_request_message"):
        assert not is_unverified(getattr(CasaApi, name))
        assert (getattr(CasaApi, name).__doc__ or "").startswith("VERIFIED")


# Casa AI -------------------------------------------------------------------


async def test_send_ai_message_generates_and_returns_key(api: CasaApi, server: FakeServer) -> None:
    payload = {
        "member_message": {
            **AI_MESSAGE,
            "parts": [
                {"type": AI_PART_TEXT, "id": "part-1", "text": "Example"},
                {"type": AI_PART_DATA_TODO, "id": "part-2", "data": {"todo_id": "todo-1"}},
                {"type": "future-part", "anything": [1, None]},
            ],
        },
        "active_response": {"message_id": "message-2", "status_message": "Working", "parts": []},
    }
    server.add("POST", f"{H}/casa_ai/messages", status=202, payload=payload)
    sent = await api.send_ai_message(HOME_ID, "Example")
    assert isinstance(sent, SentCasaAIMessage)
    assert uuid.UUID(sent.idempotency_key).version == 4
    (call,) = server.calls("POST", f"{H}/casa_ai/messages")
    assert call.headers["Idempotency-Key"] == sent.idempotency_key
    assert json.loads(call.body) == {
        "input": {"type": "message", "text": "Example", "upload_ids": []}
    }
    text, todo, future = sent.response.member_message.parts
    assert (text.type, text.text) == ("text", "Example")
    assert todo.type == "data-todo" and todo.model_extra == {"data": {"todo_id": "todo-1"}}
    assert future.type == "future-part" and future.model_extra == {"anything": [1, None]}
    assert sent.response.active_response is not None
    assert sent.response.active_response.status_message == "Working"


async def test_idempotency_key_cannot_override_auth(api: CasaApi, server: FakeServer) -> None:
    server.add("POST", f"{H}/casa_ai/messages", status=202, payload={"member_message": AI_MESSAGE})
    await api.client.request(
        "POST",
        f"{H}/casa_ai/messages",
        json={},
        headers={"authorization": "Bearer forged", "Idempotency-Key": "k"},
    )
    (call,) = server.calls("POST", f"{H}/casa_ai/messages")
    assert call.headers["Authorization"] == "Bearer synthetic-id"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": ""},
        {"text": "x" * 10_001},
        {"text": CANARY, "upload_ids": "upload-1"},
        {"text": CANARY, "upload_ids": [CANARY, 1]},
        {"text": CANARY, "idempotency_key": ""},
        {"text": CANARY, "idempotency_key": "has space"},
        {"text": CANARY, "idempotency_key": "x" * 256},
        {"text": 5},
    ],
)
async def test_send_ai_message_rejects_bad_input(
    api: CasaApi, server: FakeServer, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await api.send_ai_message(HOME_ID, **kwargs)
    _assert_scrubbed(caught.value)
    assert server.seen == []


async def test_send_ai_message_text_limit_is_inclusive(api: CasaApi, server: FakeServer) -> None:
    server.add("POST", f"{H}/casa_ai/messages", status=202, payload={"member_message": AI_MESSAGE})
    await api.send_ai_message(HOME_ID, "x" * 10_000)
    assert len(server.calls("POST", f"{H}/casa_ai/messages")) == 1


@pytest.mark.parametrize("rating", ["meh", "", None, "GOOD"])
async def test_rate_rejects_unknown_rating(api: CasaApi, server: FakeServer, rating: Any) -> None:
    with pytest.raises(CasaRequestError):
        await api.rate_ai_message(HOME_ID, "message-1", rating)
    assert server.seen == []


def test_thread_update_typed_payload() -> None:
    payload: dict[str, Any] = {
        "conversation_id": "conversation-1",
        "cursor": "opaque-cursor",
        "changes": [
            {"type": "message.upsert", "message": {**AI_MESSAGE, "sender_role": "concierge"}},
            {"type": "future.change", "message": "not-a-message", "extra": 1},
            {"no_type": True},
        ],
        "active_response": None,
        "send_to_human_target_message_id": None,
    }
    event = CasaAIThreadUpdateEvent(
        "thread.update", "1", json.dumps(payload), cast(JsonValue, payload)
    )
    update = event.update()
    assert isinstance(update, CasaAIThreadUpdate)
    upsert, unknown, untagged = update.changes
    assert isinstance(upsert, CasaAIMessageUpsertChange)
    assert upsert.message.sender_role == "concierge"
    assert isinstance(unknown, CasaAIUnknownChange)
    assert unknown.model_extra == {"message": "not-a-message", "extra": 1}
    assert isinstance(untagged, CasaAIUnknownChange) and untagged.type is None
    assert event.payload == payload  # JSON fallback untouched.


def test_thread_update_schema_drift_is_scrubbed() -> None:
    payload: JsonValue = {
        "changes": [{"type": "message.upsert", "message": {"created_at": CANARY}}]
    }
    event = CasaAIThreadUpdateEvent("thread.update", None, "", payload)
    with pytest.raises(CasaResponseError) as caught:
        event.update()
    _assert_scrubbed(caught.value)


# To-do questions -----------------------------------------------------------


async def test_answer_multi_select(api: CasaApi, server: FakeServer) -> None:
    path = f"{H}/todos/todo-1/question_rounds/round-1/questions/question-1/answer"
    server.add("PUT", path, status=204)
    answer = MultiSelectAnswer(selected_option_indexes=[1, 3], other_text="Other")
    await api.answer_todo_question(HOME_ID, "todo-1", "round-1", "question-1", answer=answer)
    (call,) = server.calls("PUT", path)
    assert json.loads(call.body) == {
        "is_skipped": False,
        "answer": {
            "kind": "multi_select",
            "other_text": "Other",
            "selected_option_indexes": [1, 3],
        },
    }


async def test_answer_skip_sends_null_answer(api: CasaApi, server: FakeServer) -> None:
    path = f"{H}/todos/todo-1/question_rounds/round-1/questions/question-1/answer"
    server.add("PUT", path, status=204)
    await api.answer_todo_question(HOME_ID, "todo-1", "round-1", "question-1", skip=True)
    (call,) = server.calls("PUT", path)
    assert json.loads(call.body) == {"is_skipped": True, "answer": None}


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"skip": True, "answer": SingleSelectAnswer(selected_option_index=0)},
        {"skip": 1},
        {"answer": {"kind": "single_select", "selected_option_index": -1}},
        {"answer": {"kind": "future", "selected_option_index": 0}},
        {
            "answer": {
                "kind": "single_select",
                "selected_option_index": 0,
                "other_text": "x" * 10_001,
            }
        },
    ],
)
async def test_answer_rejects_bad_input(
    api: CasaApi, server: FakeServer, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(CasaRequestError):
        await api.answer_todo_question(HOME_ID, "todo-1", "round-1", "question-1", **kwargs)
    assert server.seen == []


@pytest.mark.parametrize("answers", [[], "question-1", [{"question_id": "q", "input_kind": "x"}]])
async def test_submit_round_rejects_bad_answers(
    api: CasaApi, server: FakeServer, answers: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await api.submit_todo_question_round(HOME_ID, "todo-1", "round-1", answers)
    assert server.seen == []


@pytest.mark.parametrize("decision", ["", None, 1, "x" * 129])
async def test_respond_rejects_bad_decision(
    api: CasaApi, server: FakeServer, decision: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await api.respond_to_suggested_todo(HOME_ID, "suggestion-1", decision)
    assert server.seen == []


# Settings ------------------------------------------------------------------


async def test_autopilot_map_and_datetime_guard(api: CasaApi, server: FakeServer) -> None:
    path = f"{H}/autopilot/plan-1"
    server.add("PATCH", path, payload={"message": "ok"})
    await api.update_autopilot_plan(
        HOME_ID,
        "plan-1",
        enabled=False,
        selected_cadence="every_quarter",
        next_desired_occurrence_date=date(2026, 12, 1),
        associations_enabled_map={"entity-1": True, "entity-2": False},
    )
    (call,) = server.calls("PATCH", path)
    assert json.loads(call.body)["associations_enabled_map"] == {
        "entity-1": True,
        "entity-2": False,
    }
    for bad in (
        {"next_desired_occurrence_date": datetime(2026, 12, 1)},
        {"next_desired_occurrence_date": "2026-12-01"},
        {"associations_enabled_map": {"entity-1": 1}},
        {"associations_enabled_map": [("entity-1", True)]},
        {"selected_cadence": ""},
        {"enabled": "true"},
    ):
        kwargs: dict[str, Any] = {
            "enabled": True,
            "selected_cadence": "every_quarter",
            "next_desired_occurrence_date": date(2026, 12, 1),
            **bad,
        }
        with pytest.raises(CasaRequestError):
            await api.update_autopilot_plan(HOME_ID, "plan-1", **kwargs)
    assert len(server.calls("PATCH", path)) == 1


async def test_notification_settings_require_entries(api: CasaApi, server: FakeServer) -> None:
    bad_entry = {"notification_type": "x", "channel": "push", "enabled": "yes"}
    for bad in ([], [bad_entry]):
        with pytest.raises(CasaRequestError):
            await api.update_notification_settings(HOME_ID, cast(Any, bad))
    assert server.seen == []


async def test_access_preferences_require_all_keys(api: CasaApi) -> None:
    with pytest.raises(TypeError):
        await api.update_access_preferences(HOME_ID, general_instructions=None)  # type: ignore[call-arg]


# IDs -------------------------------------------------------------------------


@pytest.mark.parametrize("bad_id", ["", ".", "..", "x/y", "x?y", "x%2Fy", "x y", "x\n", None, True])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_bad_home_ids_rejected_before_io(
    api: CasaApi, server: FakeServer, case: WriteCase, bad_id: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tests.test_verified_writes.HOME_ID", bad_id)
    with pytest.raises(CasaRequestError) as caught:
        await case.call(api)
    _assert_scrubbed(caught.value)
    assert server.seen == []


@pytest.mark.parametrize(
    "call",
    [
        lambda api: api.move_entity_to_room(HOME_ID, "../x", "room-1"),
        lambda api: api.move_entity_to_room(HOME_ID, "entity-1", "a/b"),
        lambda api: api.rename_room(HOME_ID, "a/b", room_type_id="type-1", name="Room"),
        lambda api: api.update_entity_make_model(HOME_ID, "..", model_name="Model"),
        lambda api: api.rate_ai_message(HOME_ID, "a?b", "good"),
        lambda api: api.answer_todo_question(HOME_ID, "t", "r", "q#x", skip=True),
        lambda api: api.submit_todo_question_round(HOME_ID, "t", "..", []),
        lambda api: api.respond_to_suggested_todo(HOME_ID, "", "accept"),
        lambda api: api.materialize_todo(HOME_ID, "t/1"),
        lambda api: api.update_autopilot_plan(
            HOME_ID,
            "p 1",
            enabled=True,
            selected_cadence="x",
            next_desired_occurrence_date=date(2026, 1, 1),
        ),
        lambda api: api.create_document(HOME_ID, "upload-1", "bad\nname.pdf"),
        lambda api: api.create_document(HOME_ID, "", "name.pdf"),
    ],
)
async def test_bad_resource_inputs_rejected_before_io(
    api: CasaApi, server: FakeServer, call: Callable[[CasaApi], Awaitable[Any]]
) -> None:
    with pytest.raises(CasaRequestError):
        await call(api)
    assert server.seen == []


# Document upload -------------------------------------------------------------


def _upload_routes(server: FakeServer, session_url: str) -> None:
    server.add("GET", f"{H}/documents/types", payload=DOCUMENT_TYPES)
    server.add(
        "POST",
        f"{H}/documents/sessions",
        payload={"uploads": [{"upload_id": "upload-1", "session_url": session_url}]},
    )
    server.add("PUT", STORAGE_PATH, status=200)
    server.add(
        "POST", f"{H}/documents", status=201, payload={"document": DOCUMENT, "already_exists": True}
    )


async def test_upload_document_full_flow(api: CasaApi, server: FakeServer, storage: str) -> None:
    content = b"%PDF-1.4 synthetic"
    _upload_routes(server, storage)
    result = await api.upload_document(HOME_ID, content, "example.pdf", find_todos=True)
    assert result.already_exists is True and result.document.id == "document-1"
    assert [(s.method, s.path) for s in server.seen if s.path != TOKEN_PATH] == [
        ("GET", f"{H}/documents/types"),
        ("POST", f"{H}/documents/sessions"),
        ("PUT", STORAGE_PATH),
        ("POST", f"{H}/documents"),
    ]
    (session_call,) = server.calls("POST", f"{H}/documents/sessions")
    assert json.loads(session_call.body) == {
        "files": [{"size_bytes": len(content), "mimetype": "application/pdf"}]
    }
    (put,) = server.calls("PUT", STORAGE_PATH)
    assert put.body.encode() == content
    assert put.query == {"uploadType": "resumable", "upload_id": "synthetic-session"}
    assert put.headers["Content-Type"] == "application/pdf"
    assert put.headers["Content-Length"] == str(len(content))
    assert put.headers["Content-Range"] == f"bytes 0-{len(content) - 1}/{len(content)}"
    for leaked in ("Authorization", "X-Casa-App", "X-Casa-App-Version", "Idempotency-Key"):
        assert leaked not in put.headers
    (register,) = server.calls("POST", f"{H}/documents")
    assert json.loads(register.body) == {
        "find_todos": True,
        "upload_id": "upload-1",
        "original_filename": "example.pdf",
    }


async def test_upload_document_from_path(
    api: CasaApi, server: FakeServer, storage: str, tmp_path: Path
) -> None:
    source = tmp_path / "scan.png"
    source.write_bytes(b"synthetic-png")
    _upload_routes(server, storage)
    await api.upload_document(HOME_ID, source, "scan.png")
    (session_call,) = server.calls("POST", f"{H}/documents/sessions")
    assert json.loads(session_call.body)["files"][0]["mimetype"] == "image/png"
    (put,) = server.calls("PUT", STORAGE_PATH)
    assert put.body == "synthetic-png"


@pytest.mark.parametrize(
    ("source", "filename", "mimetype"),
    [
        (b"synthetic", "example.txt", None),  # Guessed text/plain, not allowed.
        (b"synthetic", "example.pdf", "application/zip"),
        (b"x" * 65, "example.pdf", None),  # Over max_file_size_bytes.
        (b"", "example.pdf", None),
    ],
)
async def test_upload_validated_against_policy_before_writes(
    api: CasaApi,
    server: FakeServer,
    storage: str,
    source: bytes,
    filename: str,
    mimetype: str | None,
) -> None:
    _upload_routes(server, storage)
    with pytest.raises(CasaRequestError):
        await api.upload_document(HOME_ID, source, filename, mimetype)
    assert [(s.method, s.path) for s in server.seen if s.path != TOKEN_PATH] == [
        ("GET", f"{H}/documents/types")
    ]


async def test_upload_rejects_oversized_path_without_reading(
    api: CasaApi, server: FakeServer, storage: str, tmp_path: Path
) -> None:
    source = tmp_path / "big.pdf"
    source.write_bytes(b"x" * 65)
    _upload_routes(server, storage)
    with pytest.raises(CasaRequestError, match="max_file_size_bytes"):
        await api.upload_document(HOME_ID, str(source), "big.pdf")
    assert not server.calls("POST", f"{H}/documents/sessions")


async def test_upload_rejects_unguessable_mimetype_before_io(
    api: CasaApi, server: FakeServer
) -> None:
    with pytest.raises(CasaRequestError):
        await api.upload_document(HOME_ID, b"x", "no-extension")
    assert server.seen == []


async def test_upload_rejects_unknown_source_type_before_io(
    api: CasaApi, server: FakeServer
) -> None:
    with pytest.raises(CasaRequestError):
        await api.upload_document(HOME_ID, 123, "example.pdf")  # type: ignore[arg-type]
    assert server.seen == []


async def test_upload_storage_failure_is_scrubbed(
    api: CasaApi, server: FakeServer, storage: str
) -> None:
    _upload_routes(server, storage)
    server.routes[("PUT", STORAGE_PATH)].clear()
    server.add("PUT", STORAGE_PATH, status=403, body=f"<Error>{CANARY}</Error>")
    with pytest.raises(CasaApiError) as caught:
        await api.upload_document(HOME_ID, b"%PDF", "example.pdf")
    assert caught.value.code == "storage_upload_failed"
    assert CANARY not in str(caught.value) and "synthetic-session" not in str(caught.value)
    assert len(server.calls("PUT", STORAGE_PATH)) == 1  # No retry.
    assert not server.calls("POST", f"{H}/documents")  # Never registered.


async def test_storage_connection_error_hides_url(
    api: CasaApi, server: FakeServer, storage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = URL(storage).with_port(1)
    monkeypatch.setattr(uploads, "STORAGE_UPLOAD_PORT", 1)
    with pytest.raises(CasaConnectionError) as caught:
        await api.upload_document_content(str(dead), b"%PDF", "application/pdf")
    assert "synthetic-session" not in str(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


async def test_upload_requires_exactly_one_session(
    api: CasaApi, server: FakeServer, storage: str
) -> None:
    server.add("GET", f"{H}/documents/types", payload=DOCUMENT_TYPES)
    server.add("POST", f"{H}/documents/sessions", payload={"uploads": []})
    with pytest.raises(CasaResponseError):
        await api.upload_document(HOME_ID, b"%PDF", "example.pdf")
    assert not server.calls("PUT", STORAGE_PATH)


@pytest.mark.parametrize(
    "url",
    [
        "http://storage.googleapis.com/upload?upload_id=SECRET",
        "https://storage.googleapis.com.example.com/upload?upload_id=SECRET",
        "https://example.com/upload?upload_id=SECRET",
        "https://user:SECRET@storage.googleapis.com/upload",
        "https://storage.googleapis.com:8443/upload?upload_id=SECRET",
        "https://evil.example/https://storage.googleapis.com/?SECRET",
        "storage.googleapis.com/upload?SECRET",
        "",
        "https://[::1/SECRET",
    ],
)
async def test_storage_url_restricted_before_io(api: CasaApi, server: FakeServer, url: str) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await api.upload_document_content(url, b"%PDF", "application/pdf")
    assert "SECRET" not in str(caught.value)
    assert caught.value.__context__ is None
    assert server.seen == []


def test_storage_url_accepts_cloud_storage() -> None:
    url = uploads.validate_storage_url(
        "https://storage.googleapis.com/upload/storage/v1/b/b/o?uploadType=resumable&upload_id=x"
    )
    assert url.host == "storage.googleapis.com"


# Read upgrades ----------------------------------------------------------------


async def test_document_thumbnail(api: CasaApi, server: FakeServer) -> None:
    path = f"{H}/documents/document-1/thumbnail"
    server.add(
        "GET",
        path,
        payload={
            "url": "https://example.invalid/thumb",
            "expires_at": 40,
            "preview_pages": ["https://example.invalid/p1"],
            "page_count_url": "https://example.invalid/count",
        },
    )
    result = await api.document_thumbnail(HOME_ID, "document-1")
    assert result.expires_at == 40 and result.preview_pages == ["https://example.invalid/p1"]
    assert not is_unverified(CasaApi.document_thumbnail)
    assert len(server.seen) == 2  # Token refresh plus the GET. URLs never fetched.


async def test_documents_populated_with_app_params(api: CasaApi, server: FakeServer) -> None:
    server.add("GET", f"{H}/documents", payload={"documents": [DOCUMENT], "next_cursor": None})
    result = await api.documents(HOME_ID, sort="uploaded")
    (call,) = server.calls("GET", f"{H}/documents")
    assert call.query == {"limit": "30", "sort": "uploaded"}
    organization = result.documents[0].organization
    assert organization is not None and organization.status == "queued"


async def test_request_details_populated(api: CasaApi, server: FakeServer) -> None:
    path = f"{H}/requests/request-1"
    server.add(
        "GET",
        path,
        payload={
            "id": "request-1",
            "type": "concierge",
            "status": "open",
            "title": "Example",
            "emoji": "x",
            "created_at": 1,
            "updated_at": 2,
            "has_unread_messages": True,
            "summary": {"scheduled_visit_count": 0, "total_spent": 0, "total_spent_display": "$0"},
            "messages": [
                {
                    "id": "m1",
                    "created_at": 3,
                    "sender_role": "concierge",
                    "sender_name": "Example Concierge",
                    "sender_avatar_url": "https://example.invalid/a",
                    "sender_avatar_cache_key": "a1",
                    "content": "Example",
                    "attachments": [],
                    "scheduling_prompt": None,
                    "availability_request": None,
                    "invoice": None,
                    "purchase_approval_requests": [],
                }
            ],
            "visits": [],
            "invoices": [],
            "purchases": [],
            "feedback": None,
        },
    )
    result = await api.request_details(HOME_ID, "request-1")
    assert isinstance(result.summary, RequestSummary)
    assert result.summary.total_spent_display == "$0"
    assert result.messages[0].sender_avatar_cache_key == "a1"
    with pytest.raises(ValueError):
        await api.request_details(HOME_ID, "../escape")


async def test_requests_tab_card_fields(api: CasaApi, server: FakeServer) -> None:
    card = {
        "id": "request-1",
        "title": "Example",
        "latest_message_preview": "Example",
        "emoji": "x",
        "updated_at": 5,
        "has_unread_messages": False,
        "pending_invoice_count": 0,
        "pending_purchase_count": 1,
        "pending_schedule_prompt_count": 0,
        "ready_to_review_availability_count": 2,
        "concierge_awaiting_reply": True,
        "type": "concierge",
        "vendor_visits": [],
    }
    server.add(
        "GET",
        f"{H}/requests_tab",
        payload={
            "requests": {"needs_review": [card], "sections": []},
            "tasks": {"sections": []},
        },
    )
    result = await api.requests_tab(HOME_ID)
    assert result.requests.needs_review[0].ready_to_review_availability_count == 2


async def test_membership_info_active(api: CasaApi, server: FakeServer) -> None:
    server.add(
        "GET",
        f"{H}/membership/info",
        payload={
            "amount": "$1",
            "amount_cents": 100,
            "benefits": [],
            "cancel_at_period_end": False,
            "current_period_end": 200,
            "current_period_start": 100,
            "interval": "month",
            "member_since": 50,
            "name": "Example",
            "next_billing_date": 200,
            "status": "active",
            "stripe_customer_id": "cus_example",
            "stripe_subscription_id": "sub_example",
        },
    )
    result = await api.membership_info(HOME_ID)
    assert result.status == "active" and result.cancel_at_period_end is False
    assert result.model_extra == {}


async def test_request_purchases_envelope(api: CasaApi, server: FakeServer) -> None:
    server.add(
        "GET",
        f"{H}/requests/request-1/purchases",
        payload={
            "context_title": "Example",
            "pending_purchase_approvals": [],
            "approved_purchases": [],
            "purchased_items": [],
            "next_package_pickup_by": 60,
        },
    )
    result = await api.request_purchases(HOME_ID, "request-1")
    assert result.next_package_pickup_by == 60


def _assert_scrubbed(error: BaseException) -> None:
    assert CANARY not in str(error)
    assert CANARY not in "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__context__ is None
