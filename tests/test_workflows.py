"""Synthetic workflow codecs and loopback-only transport tests, not live evidence."""

from __future__ import annotations

import inspect
import ipaddress
import json
import socket
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from casahome._common import is_unverified
from casahome.client import CasaClient
from casahome.exceptions import CasaApiError, CasaAuthError, CasaRequestError, CasaResponseError
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.documents import DocumentDetailsResponse, HomeDocument
from casahome.models.enums import VendorVisitStatus
from casahome.models.preferences import (
    SchedulePreferencesResponse,
    SchedulingDay,
    SchedulingTimeOfDay,
)
from casahome.models.read_todos import TodoDetailsResponse, TodoReadDetail
from casahome.models.requests import TodosLaneSection
from casahome.models.todos import TodoLaneCard
from casahome.models.workflows import (
    AnalyzeDocumentRequest,
    CancelVendorVisitResponse,
    ConfirmTodoSupportRequest,
    MemberAvailabilitySlotWindow,
    RejectSuggestedTodoRequest,
    ReorderTodoSectionRequest,
    ReorderTodoSectionResponse,
    UpdateAvailabilitySlotsRequest,
    UpdateDocumentBody,
    UpdateSchedulePreferencesRequest,
    UpdateTodoAttachmentsBody,
    UpdateTodoBody,
)
from casahome.workflows import ProvisionalWorkflowMixin
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer

H = f"/protected/home/{HOME_ID}"
CANARY = "SYNTHETIC-PRIVATE-INPUT"
TOKEN = {
    "access_token": "synthetic-access",
    "expires_in": "3600",
    "token_type": "Bearer",
    "refresh_token": "synthetic-refresh",
    "id_token": "synthetic-id",
    "user_id": "synthetic-user",
    "project_id": "synthetic-project",
}
TODO = {
    "todo": {
        "id": "todo-1",
        "title": "Example task",
        "emoji": "x",
        "original_text": "Example input",
        "prepared_brief": "Example brief",
        "status": "preparing",
        "creator_role": "member",
        "created_at": 10,
        "updated_at": 11,
        "question_rounds": [{"id": "round-1", "sequence": 1, "state": "answered"}],
    }
}
DOCUMENT = {
    "document": {
        "id": "document-1",
        "name": "Example document",
        "document_type": "other",
        "document_date": None,
        "organization": {"id": "organization-1", "status": "queued"},
    }
}
PREFERENCES = {
    "days_of_week": [{"day_of_week": 3, "label": "Example day", "enabled": True}],
    "times_of_day": [
        {
            "id": "window-1",
            "window_title": "Example",
            "window_time_range": "Example",
            "enabled": True,
        }
    ],
}
AVAILABILITY = {
    "availability_request": {
        "id": "availability-1",
        "request_id": "request-1",
        "home_id": HOME_ID,
        "status": "example-status",
        "slot_count": 1,
        "created_at": 10,
    },
    "slots": [
        {
            "id": "slot-1",
            "member_availability_request_id": "availability-1",
            "start_time": 5,
            "end_time": 7,
        }
    ],
    "home_timezone": "Example/Zone",
    "constraints": {
        "snap_minutes": 10,
        "min_slot_minutes": 20,
        "default_duration_minutes": 30,
        "lead_time_minutes": 40,
    },
}
REORDERED = {
    "section": {
        "name": "ready_for_scheduling",
        "title": "Example section",
        "order_revision": 4,
        "items": [
            {
                "kind": "todo",
                "id": "todo-1",
                "title": "Example task",
                "emoji": "x",
                "updated_at": 10,
                "state": "ready_for_scheduling",
            }
        ],
    }
}
CANCELED = {"id": "visit-1", "status": "future-cancellation-status"}


class TestApi(ProvisionalWorkflowMixin):
    """Test the isolated mixin without modifying parent API wiring."""

    __test__ = False

    def __init__(self, client: CasaClient) -> None:
        self.client = client


@dataclass
class Call:
    method: str
    path: str
    body: Any


class FakeClient(CasaClient):
    """No session, auth, sockets or external state."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[Call] = []

    async def post(self, path: str, *, json: Any = None, retry_on_401: bool = False) -> Any:
        assert retry_on_401 is False
        self.calls.append(Call("POST", path, json))
        return self.response

    async def patch(self, path: str, *, json: Any = None) -> Any:
        self.calls.append(Call("PATCH", path, json))
        return self.response

    async def put(self, path: str, *, json: Any = None) -> Any:
        self.calls.append(Call("PUT", path, json))
        return self.response


@dataclass
class WorkflowCase:
    name: str
    method: str
    suffix: str
    body: Any
    response: Any
    model: type[BaseModel]
    kwargs: dict[str, Any] = field(default_factory=dict)

    async def invoke(self, api: TestApi, **overrides: Any) -> BaseModel:
        args = {"home_id": HOME_ID, **self.kwargs, **overrides}
        result: BaseModel = await getattr(api, self.name)(**args)
        return result

    @property
    def path(self) -> str:
        return H + self.suffix


CASES = [
    WorkflowCase(
        "update_todo",
        "PATCH",
        "/todos/todo-1",
        {},
        TODO,
        TodoDetailsResponse,
        {"todo_id": "todo-1", "body": UpdateTodoBody()},
    ),
    WorkflowCase(
        "reject_suggested_todo",
        "POST",
        "/suggested_todos/todo-1/respond",
        {"decision": "reject"},
        TODO,
        TodoDetailsResponse,
        {"todo_id": "todo-1"},
    ),
    WorkflowCase(
        "confirm_todo_support",
        "POST",
        "/todos/todo-1/support_confirmation",
        {"is_support_question": False},
        TODO,
        TodoDetailsResponse,
        {"todo_id": "todo-1", "is_support_question": False},
    ),
    WorkflowCase(
        "update_document",
        "PATCH",
        "/documents/document-1",
        {},
        DOCUMENT,
        DocumentDetailsResponse,
        {"document_id": "document-1", "body": UpdateDocumentBody()},
    ),
    WorkflowCase(
        "analyze_document",
        "POST",
        "/documents/document-1/analysis",
        {"reanalyze": False},
        DOCUMENT,
        DocumentDetailsResponse,
        {"document_id": "document-1", "reanalyze": False},
    ),
    WorkflowCase(
        "organize_document",
        "POST",
        "/documents/document-1/organization",
        None,
        DOCUMENT,
        DocumentDetailsResponse,
        {"document_id": "document-1"},
    ),
    WorkflowCase(
        "update_schedule_preferences",
        "PUT",
        "/schedule_preferences",
        {"selected_days_of_week": [], "selected_times_of_day": []},
        PREFERENCES,
        SchedulePreferencesResponse,
        {
            "body": UpdateSchedulePreferencesRequest(
                selected_days_of_week=[], selected_times_of_day=[]
            )
        },
    ),
    WorkflowCase(
        "update_availability_slots",
        "PUT",
        "/availability_requests/availability-1/slots",
        {"slots": []},
        AVAILABILITY,
        MemberAvailabilityDetail,
        {"availability_request_id": "availability-1", "windows": []},
    ),
    WorkflowCase(
        "reorder_todo_section",
        "PUT",
        "/requests_tab/todo_sections/ready_for_scheduling/order",
        {"expected_revision": 3, "ordered_item_ids": ["todo-1"]},
        REORDERED,
        ReorderTodoSectionResponse,
        {"section": "ready_for_scheduling", "expected_revision": 3, "ordered_item_ids": ["todo-1"]},
    ),
    WorkflowCase(
        "retry_todo",
        "POST",
        "/todos/todo-1/retry",
        None,
        TODO,
        TodoDetailsResponse,
        {"todo_id": "todo-1"},
    ),
    WorkflowCase(
        "cancel_vendor_visit",
        "PUT",
        "/vendor_visits/visit-1/cancelation",
        None,
        CANCELED,
        CancelVendorVisitResponse,
        {"visit_id": "visit-1"},
    ),
]
BY_NAME = {case.name: case for case in CASES}


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    getaddrinfo = socket.getaddrinfo

    def check(address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else address
        try:
            allowed = ipaddress.ip_address(host).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise AssertionError("Workflow tests forbid non-loopback network access")

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        check(address)
        connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        check(address)
        return connect_ex(sock, address)

    def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        check(host)
        return getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


def assert_scrubbed(error: BaseException) -> None:
    assert error.__context__ is None
    assert error.__cause__ is None
    assert CANARY not in str(error)
    assert CANARY not in "".join(traceback.format_exception(error))


def test_non_loopback_access_is_blocked() -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match="non-loopback"):
        sock.connect(("192.0.2.1", 443))
    with socket.socket() as sock, pytest.raises(AssertionError, match="non-loopback"):
        sock.connect_ex(("192.0.2.1", 443))
    with pytest.raises(AssertionError, match="non-loopback"):
        socket.getaddrinfo("example.invalid", 443)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_synthetic_typed_response_and_exact_body(case: WorkflowCase) -> None:
    fake = FakeClient(case.response)
    result = await case.invoke(TestApi(fake))
    assert isinstance(result, case.model)
    assert fake.calls == [Call(case.method, case.path, case.body)]
    assert is_unverified(getattr(ProvisionalWorkflowMixin, case.name))
    if isinstance(result, TodoDetailsResponse):
        assert isinstance(result.todo, TodoReadDetail)
        assert result.todo.question_rounds[0].id == "round-1"
    elif isinstance(result, DocumentDetailsResponse):
        assert isinstance(result.document, HomeDocument)
        assert result.document.organization is not None
        assert result.document.organization.status == "queued"
    elif isinstance(result, SchedulePreferencesResponse):
        assert isinstance(result.days_of_week[0], SchedulingDay)
        assert isinstance(result.times_of_day[0], SchedulingTimeOfDay)
    elif isinstance(result, ReorderTodoSectionResponse):
        assert isinstance(result.section, TodosLaneSection)
        assert isinstance(result.section.items[0], TodoLaneCard)
        assert result.section.order_revision == 4
    elif isinstance(result, CancelVendorVisitResponse):
        assert result.status == "future-cancellation-status"
    elif isinstance(result, MemberAvailabilityDetail):
        assert result.slots[0].start_time == 5


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_real_client_loopback_wire(
    case: WorkflowCase, client: CasaClient, server: FakeServer
) -> None:
    server.add("POST", TOKEN_PATH, payload=TOKEN)
    server.add(case.method, case.path, payload=case.response)
    result = await case.invoke(TestApi(client))
    assert isinstance(result, case.model)
    calls = server.calls(case.method, case.path)
    assert len(calls) == 1
    assert len(server.calls("POST", TOKEN_PATH)) == 1
    assert server.seen[0].path == TOKEN_PATH
    assert calls[0].query == {}
    if case.body is None:
        assert calls[0].body == ""
        assert calls[0].headers.get("Content-Type") != "application/json"
    else:
        assert json.loads(calls[0].body) == case.body
        assert calls[0].headers["Content-Type"] == "application/json"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_401_is_one_attempt(
    case: WorkflowCase, client: CasaClient, server: FakeServer
) -> None:
    server.add("POST", TOKEN_PATH, payload=TOKEN)
    server.add(case.method, case.path, status=401, body=CANARY)
    server.add(case.method, case.path, payload=case.response)
    with pytest.raises(CasaAuthError) as caught:
        await case.invoke(TestApi(client))
    assert_scrubbed(caught.value)
    assert len(server.calls(case.method, case.path)) == 1
    assert len(server.calls("POST", TOKEN_PATH)) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("status", [409, 500])
async def test_other_failures_are_not_retried(
    case: WorkflowCase, status: int, client: CasaClient, server: FakeServer
) -> None:
    server.add("POST", TOKEN_PATH, payload=TOKEN)
    server.add(case.method, case.path, status=status, body=CANARY)
    server.add(case.method, case.path, payload=case.response)
    with pytest.raises(CasaApiError) as caught:
        await case.invoke(TestApi(client))
    assert_scrubbed(caught.value)
    assert len(server.calls(case.method, case.path)) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("response", [None, {}, [], {"todo": None}, {"document": None}, CANARY])
async def test_no_raw_response_fallback(case: WorkflowCase, response: Any) -> None:
    fake = FakeClient(response)
    with pytest.raises(CasaResponseError) as caught:
        await case.invoke(TestApi(fake))
    assert_scrubbed(caught.value)
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "body,expected",
    [
        (UpdateTodoBody(title=None, prepared_brief=None, emoji=None, attachments=None), {}),
        (
            UpdateTodoBody(title="", prepared_brief="", emoji=""),
            {"title": "", "prepared_brief": "", "emoji": ""},
        ),
        (UpdateTodoBody(attachments=UpdateTodoAttachmentsBody()), {"attachments": {}}),
        (
            UpdateTodoBody(attachments=UpdateTodoAttachmentsBody(add_upload_ids=[])),
            {"attachments": {"add_upload_ids": []}},
        ),
        (
            UpdateTodoBody(attachments=UpdateTodoAttachmentsBody(remove_attachment_ids=[])),
            {"attachments": {"remove_attachment_ids": []}},
        ),
        (
            UpdateTodoBody(
                title="Replacement",
                attachments=UpdateTodoAttachmentsBody(
                    add_upload_ids=["upload-1"], remove_attachment_ids=["attachment-1"]
                ),
            ),
            {
                "title": "Replacement",
                "attachments": {
                    "add_upload_ids": ["upload-1"],
                    "remove_attachment_ids": ["attachment-1"],
                },
            },
        ),
    ],
)
async def test_todo_omission_and_attachment_deltas(body: UpdateTodoBody, expected: Any) -> None:
    fake = FakeClient(TODO)
    await TestApi(fake).update_todo(HOME_ID, "todo-1", body)
    assert fake.calls[0].body == expected


@pytest.mark.parametrize(
    "body,expected",
    [
        (UpdateDocumentBody(), {}),
        (UpdateDocumentBody(name="Warranty"), {"name": "Warranty"}),
        (UpdateDocumentBody(name=None, document_type=None), {}),
        (UpdateDocumentBody(name="", document_type=""), {"name": "", "document_type": ""}),
        (UpdateDocumentBody(document_date=None), {"document_date": None}),
        (
            UpdateDocumentBody(name=None, document_type=None, document_date=None),
            {"document_date": None},
        ),
        (UpdateDocumentBody(document_date="opaque-date"), {"document_date": "opaque-date"}),
        (UpdateDocumentBody(document_date=""), {"document_date": ""}),
        (UpdateDocumentBody().model_copy(update={"name": "Warranty"}), {"name": "Warranty"}),
        (UpdateDocumentBody().model_copy(update={"document_date": None}), {"document_date": None}),
        (UpdateDocumentBody.model_construct(name="Warranty"), {"name": "Warranty"}),
    ],
)
async def test_document_date_tristate(body: UpdateDocumentBody, expected: Any) -> None:
    fake = FakeClient(DOCUMENT)
    await TestApi(fake).update_document(HOME_ID, "document-1", body)
    assert fake.calls[0].body == expected


async def test_assignment_makes_date_clear_explicit() -> None:
    body = UpdateDocumentBody(name="Warranty")
    assert "document_date" not in body.model_fields_set
    body.document_date = None
    fake = FakeClient(DOCUMENT)
    await TestApi(fake).update_document(HOME_ID, "document-1", body)
    assert fake.calls[0].body == {"name": "Warranty", "document_date": None}


@pytest.mark.parametrize("reason", [None, "dismissed", "already_handled"])
async def test_rejection_reason_wire_values(reason: Any) -> None:
    fake = FakeClient(TODO)
    await TestApi(fake).reject_suggested_todo(HOME_ID, "todo-1", reason)
    assert fake.calls[0].body == {"decision": "reject", **({"reason": reason} if reason else {})}


@pytest.mark.parametrize(
    "name,key", [("confirm_todo_support", "is_support_question"), ("analyze_document", "reanalyze")]
)
@pytest.mark.parametrize("value", [False, True])
async def test_required_boolean_wire_values(name: str, key: str, value: bool) -> None:
    case = BY_NAME[name]
    fake = FakeClient(case.response)
    await case.invoke(TestApi(fake), **{key: value})
    assert fake.calls[0].body == {key: value}
    assert inspect.signature(getattr(ProvisionalWorkflowMixin, name)).parameters[key].default is (
        inspect.Parameter.empty
    )


async def test_integer_windows_are_not_datetime_codecs_or_overlap_policy() -> None:
    fake = FakeClient(AVAILABILITY)
    windows = [
        MemberAvailabilitySlotWindow(start_time=-7, end_time=-9),
        MemberAvailabilitySlotWindow(start_time=3, end_time=3),
        MemberAvailabilitySlotWindow(start_time=2, end_time=8),
        MemberAvailabilitySlotWindow(start_time=4, end_time=7),
    ]
    await TestApi(fake).update_availability_slots(HOME_ID, "availability-1", windows)
    assert fake.calls[0].body == {"slots": [window.model_dump() for window in windows]}


async def test_schedule_lists_are_not_numbered_sorted_or_deduplicated() -> None:
    fake = FakeClient(PREFERENCES)
    body = UpdateSchedulePreferencesRequest(
        selected_days_of_week=[15, -1, 15],
        selected_times_of_day=["window-2", "window-1", "window-2"],
    )
    await TestApi(fake).update_schedule_preferences(HOME_ID, body)
    assert fake.calls[0].body == body.model_dump()


@pytest.mark.parametrize("section", ["ready_for_scheduling", "send_to_concierge"])
@pytest.mark.parametrize("ordered", [[], ["todo-2", "todo-1", "todo-2"]])
async def test_reorder_preserves_guard_order_and_empty_list(
    section: Any, ordered: list[str]
) -> None:
    fake = FakeClient(REORDERED)
    await TestApi(fake).reorder_todo_section(
        HOME_ID, section, expected_revision=-1, ordered_item_ids=ordered
    )
    assert fake.calls == [
        Call(
            "PUT",
            f"{H}/requests_tab/todo_sections/{section}/order",
            {"expected_revision": -1, "ordered_item_ids": ordered},
        )
    ]


def test_reorder_requires_both_guard_and_ids() -> None:
    signature = inspect.signature(ProvisionalWorkflowMixin.reorder_todo_section)
    for key in ("expected_revision", "ordered_item_ids"):
        assert signature.parameters[key].default is inspect.Parameter.empty


def test_cancellation_status_is_open_not_a_success_flag() -> None:
    known = CancelVendorVisitResponse.model_validate({"id": "visit-1", "status": "canceled"})
    assert known.status is VendorVisitStatus.CANCELED
    future = CancelVendorVisitResponse.model_validate(CANCELED)
    assert type(future.status) is str
    for payload in ({"id": "visit-1"}, {"status": "canceled"}, {"id": "visit-1", "status": None}):
        with pytest.raises(ValidationError):
            CancelVendorVisitResponse.model_validate(payload)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize(
    "invalid",
    [
        "",
        ".",
        "..",
        "a/b",
        "a?b",
        "a#b",
        "a%b",
        "a b",
        "é",
        "a\n",
        "a\x7f",
        "x" * 2049,
        None,
        True,
        [],
    ],
)
async def test_all_path_ids_are_validated(case: WorkflowCase, invalid: Any) -> None:
    targets = ["home_id", *(key for key in case.kwargs if key.endswith("_id") or key == "section")]
    for key in targets:
        fake = FakeClient(case.response)
        with pytest.raises(CasaRequestError) as caught:
            await case.invoke(TestApi(fake), **{key: invalid})
        assert_scrubbed(caught.value)
        assert fake.calls == []


INVALID_INPUTS: list[tuple[str, dict[str, Any]]] = [
    ("update_todo", {"body": None}),
    ("update_todo", {"body": {"title": CANARY}}),
    ("update_todo", {"body": UpdateTodoBody().model_copy(update={"title": [CANARY]})}),
    ("update_todo", {"body": UpdateTodoBody().model_copy(update={"unknown": CANARY})}),
    (
        "update_todo",
        {
            "body": UpdateTodoBody().model_copy(
                update={
                    "attachments": UpdateTodoAttachmentsBody().model_copy(
                        update={"unknown": CANARY}
                    )
                }
            )
        },
    ),
    (
        "update_todo",
        {
            "body": UpdateTodoBody().model_copy(
                update={"attachments": {"add_upload_ids": [f"{CANARY}/unsafe"]}}
            )
        },
    ),
    ("reject_suggested_todo", {"reason": "alreadyHandled"}),
    ("reject_suggested_todo", {"reason": "accept"}),
    ("reject_suggested_todo", {"reason": [CANARY]}),
    ("confirm_todo_support", {"is_support_question": 1}),
    ("confirm_todo_support", {"is_support_question": "false"}),
    ("confirm_todo_support", {"is_support_question": None}),
    ("update_document", {"body": None}),
    ("update_document", {"body": {"document_date": None}}),
    ("update_document", {"body": UpdateDocumentBody().model_copy(update={"name": [CANARY]})}),
    ("update_document", {"body": UpdateDocumentBody().model_copy(update={"unknown": CANARY})}),
    (
        "update_document",
        {
            "body": UpdateDocumentBody().model_copy(
                update={"document_date": datetime(2000, 1, 1, tzinfo=UTC)}
            )
        },
    ),
    ("analyze_document", {"reanalyze": 0}),
    ("analyze_document", {"reanalyze": CANARY}),
    ("analyze_document", {"reanalyze": None}),
    ("update_schedule_preferences", {"body": None}),
    (
        "update_schedule_preferences",
        {
            "body": UpdateSchedulePreferencesRequest.model_construct(
                selected_days_of_week=[True], selected_times_of_day=[]
            )
        },
    ),
    (
        "update_schedule_preferences",
        {
            "body": UpdateSchedulePreferencesRequest.model_construct(
                selected_days_of_week=[], selected_times_of_day=[f"{CANARY}/unsafe"]
            )
        },
    ),
    (
        "update_schedule_preferences",
        {
            "body": UpdateSchedulePreferencesRequest.model_construct(
                selected_days_of_week=[], selected_times_of_day=[]
            ).model_copy(update={"unknown": CANARY})
        },
    ),
    ("update_availability_slots", {"windows": None}),
    ("update_availability_slots", {"windows": CANARY}),
    (
        "update_availability_slots",
        {"windows": [MemberAvailabilitySlotWindow.model_construct(start_time=True, end_time=1)]},
    ),
    ("update_availability_slots", {"windows": [{"start_time": 1, "end_time": None}]}),
    ("update_availability_slots", {"windows": [{"start_time": "1", "end_time": 2}]}),
    (
        "update_availability_slots",
        {"windows": [{"start_time": datetime(2000, 1, 1, tzinfo=UTC), "end_time": 2}]},
    ),
    (
        "update_availability_slots",
        {
            "windows": [
                MemberAvailabilitySlotWindow(start_time=1, end_time=2).model_copy(
                    update={"unknown": CANARY}
                )
            ]
        },
    ),
    ("reorder_todo_section", {"section": "pending"}),
    ("reorder_todo_section", {"expected_revision": True}),
    ("reorder_todo_section", {"expected_revision": "3"}),
    ("reorder_todo_section", {"expected_revision": None}),
    ("reorder_todo_section", {"ordered_item_ids": None}),
    ("reorder_todo_section", {"ordered_item_ids": CANARY}),
    ("reorder_todo_section", {"ordered_item_ids": [f"{CANARY}/unsafe"]}),
    ("reorder_todo_section", {"ordered_item_ids": [1]}),
]


@pytest.mark.parametrize("name,overrides", INVALID_INPUTS)
async def test_invalid_inputs_fail_before_auth_or_write(
    name: str, overrides: dict[str, Any], client: CasaClient, server: FakeServer
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await BY_NAME[name].invoke(TestApi(client), **overrides)
    assert_scrubbed(caught.value)
    assert server.seen == []


WRITE_SCHEMAS: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (UpdateTodoBody, {}),
    (UpdateTodoAttachmentsBody, {}),
    (RejectSuggestedTodoRequest, {}),
    (ConfirmTodoSupportRequest, {"is_support_question": False}),
    (UpdateDocumentBody, {}),
    (AnalyzeDocumentRequest, {"reanalyze": False}),
    (UpdateSchedulePreferencesRequest, {"selected_days_of_week": [], "selected_times_of_day": []}),
    (MemberAvailabilitySlotWindow, {"start_time": 1, "end_time": 2}),
    (UpdateAvailabilitySlotsRequest, {"slots": []}),
    (ReorderTodoSectionRequest, {"expected_revision": 1, "ordered_item_ids": []}),
]


@pytest.mark.parametrize(
    "schema,data", WRITE_SCHEMAS, ids=lambda item: getattr(item, "__name__", "")
)
def test_every_write_schema_forbids_extras(schema: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({**data, "unknown": CANARY})


@pytest.mark.parametrize(
    "schema,data",
    [
        (UpdateSchedulePreferencesRequest, {"selected_times_of_day": []}),
        (UpdateSchedulePreferencesRequest, {"selected_days_of_week": []}),
        (ConfirmTodoSupportRequest, {}),
        (AnalyzeDocumentRequest, {}),
        (MemberAvailabilitySlotWindow, {"end_time": 1}),
        (MemberAvailabilitySlotWindow, {"start_time": 1}),
        (UpdateAvailabilitySlotsRequest, {}),
        (ReorderTodoSectionRequest, {"expected_revision": 1}),
        (ReorderTodoSectionRequest, {"ordered_item_ids": []}),
    ],
)
def test_required_write_fields_have_no_defaults(
    schema: type[BaseModel], data: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(data)


@pytest.mark.parametrize("field_name", ["title", "prepared_brief", "emoji"])
async def test_todo_text_policy_is_checked_at_boundary(field_name: str) -> None:
    fake = FakeClient(TODO)
    body = UpdateTodoBody().model_copy(update={field_name: "x" * 10001})
    with pytest.raises(CasaRequestError):
        await TestApi(fake).update_todo(HOME_ID, "todo-1", body)
    assert fake.calls == []


@pytest.mark.parametrize("field_name", ["name", "document_type", "document_date"])
async def test_document_text_policy_is_checked_at_boundary(field_name: str) -> None:
    fake = FakeClient(DOCUMENT)
    body = UpdateDocumentBody().model_copy(update={field_name: "x" * 10001})
    with pytest.raises(CasaRequestError):
        await TestApi(fake).update_document(HOME_ID, "document-1", body)
    assert fake.calls == []


@pytest.mark.parametrize(
    "name,overrides",
    [
        (
            "update_todo",
            {
                "body": UpdateTodoBody.model_construct(
                    attachments=UpdateTodoAttachmentsBody().model_copy(
                        update={"add_upload_ids": ["upload-1"] * 101}
                    )
                )
            },
        ),
        (
            "update_todo",
            {
                "body": UpdateTodoBody.model_construct(
                    attachments=UpdateTodoAttachmentsBody().model_copy(
                        update={"remove_attachment_ids": ["attachment-1"] * 101}
                    )
                )
            },
        ),
        (
            "update_schedule_preferences",
            {
                "body": UpdateSchedulePreferencesRequest.model_construct(
                    selected_days_of_week=[1] * 101, selected_times_of_day=[]
                )
            },
        ),
        (
            "update_schedule_preferences",
            {
                "body": UpdateSchedulePreferencesRequest.model_construct(
                    selected_days_of_week=[], selected_times_of_day=["window-1"] * 101
                )
            },
        ),
        (
            "update_availability_slots",
            {"windows": [MemberAvailabilitySlotWindow(start_time=1, end_time=2)] * 101},
        ),
        ("reorder_todo_section", {"ordered_item_ids": ["todo-1"] * 101}),
    ],
)
async def test_list_policy_is_checked_at_boundary(name: str, overrides: dict[str, Any]) -> None:
    fake = FakeClient(BY_NAME[name].response)
    with pytest.raises(CasaRequestError):
        await BY_NAME[name].invoke(TestApi(fake), **overrides)
    assert fake.calls == []


def test_unrecovered_methods_are_not_invented() -> None:
    for name in (
        "update_request",
        "submit_availability",
        "schedule_request",
        "dismiss_document_structure_suggestion",
        "dismiss_document_work_suggestion",
        "respond_to_suggested_todo",
    ):
        assert not hasattr(ProvisionalWorkflowMixin, name)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("body", ["", "null", "{}", "not-json-SYNTHETIC-PRIVATE-INPUT"])
async def test_real_client_bad_response_is_scrubbed(
    case: WorkflowCase, body: str, client: CasaClient, server: FakeServer
) -> None:
    server.add("POST", TOKEN_PATH, payload=TOKEN)
    server.add(case.method, case.path, body=body)
    with pytest.raises((CasaApiError, CasaResponseError)) as caught:
        await case.invoke(TestApi(client))
    assert_scrubbed(caught.value)
    assert len(server.calls(case.method, case.path)) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_bad_id_fails_before_real_auth(
    case: WorkflowCase, client: CasaClient, server: FakeServer
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await case.invoke(TestApi(client), home_id=f"{CANARY}/unsafe")
    assert_scrubbed(caught.value)
    assert server.seen == []


@pytest.mark.parametrize(
    "schema,field_name,data",
    [
        (UpdateTodoBody, "title", {}),
        (UpdateTodoBody, "prepared_brief", {}),
        (UpdateTodoBody, "emoji", {}),
        (UpdateDocumentBody, "name", {}),
        (UpdateDocumentBody, "document_type", {}),
        (UpdateDocumentBody, "document_date", {}),
        (ConfirmTodoSupportRequest, "is_support_question", {}),
        (AnalyzeDocumentRequest, "reanalyze", {}),
        (MemberAvailabilitySlotWindow, "start_time", {"end_time": 1}),
        (MemberAvailabilitySlotWindow, "end_time", {"start_time": 1}),
        (ReorderTodoSectionRequest, "expected_revision", {"ordered_item_ids": []}),
    ],
)
def test_scalar_fields_do_not_coerce(
    schema: type[BaseModel], field_name: str, data: dict[str, Any]
) -> None:
    for value in (1.5, b"1", [CANARY], {"value": CANARY}):
        with pytest.raises(ValidationError):
            schema.model_validate({**data, field_name: value})


@pytest.mark.parametrize(
    "schema,field_name,data",
    [
        (UpdateTodoAttachmentsBody, "add_upload_ids", {}),
        (UpdateTodoAttachmentsBody, "remove_attachment_ids", {}),
        (UpdateSchedulePreferencesRequest, "selected_days_of_week", {"selected_times_of_day": []}),
        (UpdateSchedulePreferencesRequest, "selected_times_of_day", {"selected_days_of_week": []}),
        (UpdateAvailabilitySlotsRequest, "slots", {}),
        (ReorderTodoSectionRequest, "ordered_item_ids", {"expected_revision": 1}),
    ],
)
def test_request_models_require_actual_lists(
    schema: type[BaseModel], field_name: str, data: dict[str, Any]
) -> None:
    values: tuple[Any, ...] = ((), "", {}, set())
    for value in values:
        with pytest.raises(ValidationError):
            schema.model_validate({**data, field_name: value})


def test_safety_policy_accepts_exact_limits() -> None:
    text = "x" * 10000
    assert UpdateTodoBody(title=text, prepared_brief=text, emoji=text).title == text
    assert UpdateDocumentBody(name=text, document_type=text, document_date=text).name == text
    assert (
        len(UpdateTodoAttachmentsBody(add_upload_ids=["upload-1"] * 100).add_upload_ids or [])
        == 100
    )
    assert (
        len(
            UpdateTodoAttachmentsBody(
                remove_attachment_ids=["attachment-1"] * 100
            ).remove_attachment_ids
            or []
        )
        == 100
    )
    preferences = UpdateSchedulePreferencesRequest(
        selected_days_of_week=[1] * 100, selected_times_of_day=["window-1"] * 100
    )
    assert len(preferences.selected_days_of_week) == len(preferences.selected_times_of_day) == 100
    windows = UpdateAvailabilitySlotsRequest(
        slots=[MemberAvailabilitySlotWindow(start_time=1, end_time=2)] * 100
    )
    assert len(windows.slots) == 100
    reorder = ReorderTodoSectionRequest(expected_revision=1, ordered_item_ids=["todo-1"] * 100)
    assert len(reorder.ordered_item_ids) == 100
