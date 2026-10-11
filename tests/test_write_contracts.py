"""Entirely synthetic write tests. Network is restricted to the FakeServer fixture.

No environment, credentials, live Casa/Firebase or browser access.
No test result establishes server acceptance or authorization.
"""

from __future__ import annotations

import inspect
import ipaddress
import json
import socket
import traceback
from copy import deepcopy
from typing import Any, get_type_hints

import pytest
from pydantic import BaseModel, ValidationError

from casahome import (
    CasaApi,
    CasaApiError,
    CasaAuthError,
    CasaRequestError,
    CasaResponseError,
    is_unverified,
    models,
)
from casahome.models import (
    AttachMediaPayload,
    BasicMessageResponse,
    CreateTodoBody,
    CreateTodoResponse,
    RequestMessage,
    SendRequestMessageRequest,
    SendRequestMessageResponse,
    TodoDetail,
    UpdateEntityPropertiesRequest,
    UpdateEntityProperty,
    UpdateMultiEnumProperty,
    write_contracts,
)
from casahome.models.todos import AttachMediaPayload as LegacyAttachments
from casahome.models.todos import CreateTodoBody as LegacyTodoBody
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer

H = f"/protected/home/{HOME_ID}"
MH = f"/protected/member/home/{HOME_ID}"
TODO: dict[str, Any] = {
    "id": "todo-test",
    "title": "Synthetic task",
    "emoji": "x",
    "original_text": "Synthetic input",
    "prepared_brief": "",
    "status": "preparing",
    "creator_role": "member",
    "created_at": 10,
    "updated_at": 11,
    "future_todo_field": {"nested": []},
}
MESSAGE: dict[str, Any] = {
    "id": "message-test",
    "created_at": 12,
    "sender_role": "member",
    "sender_name": "Example Person",
    "content": "Synthetic reply",
    "attachments": [{"future_media_variant": {"id": "media-test"}}],
    "future_message_field": {"nested": None},
}
TOKEN: dict[str, str] = {
    "access_token": "synthetic-access",
    "expires_in": "3600",
    "token_type": "Bearer",
    "refresh_token": "synthetic-refresh",
    "id_token": "synthetic-id",
    "user_id": "synthetic-user",
    "project_id": "synthetic-project",
}
CANARY = "SYNTHETIC-PRIVATE-INPUT-NOT-A-CREDENTIAL"
INVALID_FLAGS: tuple[Any, ...] = (0, 1, "false", "true", [], {})
INPUT_MODELS = (
    AttachMediaPayload,
    CreateTodoBody,
    SendRequestMessageRequest,
    UpdateMultiEnumProperty,
    UpdateEntityProperty,
    UpdateEntityPropertiesRequest,
)
WRITE_METHODS = (
    "create_todo",
    "create_todo_result",
    "send_request_message",
    "update_entity_properties",
)


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
            raise AssertionError("Write tests forbid non-loopback network access")

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


@pytest.fixture(autouse=True)
def synthetic_token(server: FakeServer) -> None:
    server.add("POST", TOKEN_PATH, payload=TOKEN)


async def invoke(api: CasaApi, name: str, **kwargs: Any) -> BaseModel:
    """Typed synthetic defaults, with overrides for pre-I/O validation tests."""
    args: dict[str, Any] = {"home_id": HOME_ID}
    if name in {"create_todo", "create_todo_result"}:
        args["body"] = CreateTodoBody(content="Synthetic input")
    elif name == "send_request_message":
        args.update(request_id="request-test", body=SendRequestMessageRequest())
    elif name == "update_entity_properties":
        args.update(entity_id="entity-test", body=UpdateEntityPropertiesRequest(props=[]))
    else:
        raise AssertionError("Unknown synthetic write method")
    args.update(kwargs)
    result: BaseModel = await getattr(api, name)(**args)
    return result


def operation(name: str) -> tuple[str, str, dict[str, Any]]:
    if name in {"create_todo", "create_todo_result"}:
        return "POST", f"{H}/todos", {"todo": TODO, "needs_support_confirmation": True}
    if name == "send_request_message":
        return "POST", f"{H}/requests/request-test/messages", {"message": MESSAGE}
    if name == "update_entity_properties":
        return "PATCH", f"{MH}/entity/entity-test/props", {"message": "Synthetic status"}
    raise AssertionError("Unknown synthetic write method")


@pytest.mark.parametrize("name", WRITE_METHODS)
def test_write_methods_evidence_markers(name: str) -> None:
    method = getattr(CasaApi, name)
    assert inspect.iscoroutinefunction(method)
    verified = name in {"create_todo", "create_todo_result", "send_request_message"}
    assert is_unverified(method) is not verified
    assert (method.__doc__ or "").startswith("VERIFIED" if verified else "UNVERIFIED")
    assert ("observed" if verified else "static") in (method.__doc__ or "").lower()


@pytest.mark.parametrize(
    ("name", "response"),
    [
        ("create_todo", TodoDetail),
        ("create_todo_result", CreateTodoResponse),
        ("send_request_message", SendRequestMessageResponse),
        ("update_entity_properties", BasicMessageResponse),
    ],
)
def test_method_annotations(name: str, response: type[BaseModel]) -> None:
    hints = get_type_hints(getattr(CasaApi, name))
    assert hints["return"] is response
    assert hints["home_id"] is str
    assert (
        hints["body"]
        is {
            "create_todo": LegacyTodoBody,
            "create_todo_result": LegacyTodoBody,
            "send_request_message": SendRequestMessageRequest,
            "update_entity_properties": UpdateEntityPropertiesRequest,
        }[name]
    )


def test_exports_reuse_existing_response_models() -> None:
    for model in (
        *INPUT_MODELS,
        CreateTodoResponse,
        SendRequestMessageResponse,
        BasicMessageResponse,
    ):
        assert getattr(models, model.__name__) is model
        assert getattr(write_contracts, model.__name__) is model
        assert model.__name__ in models.__all__
    assert CreateTodoResponse.model_fields["todo"].annotation is TodoDetail
    assert SendRequestMessageResponse.model_fields["message"].annotation is RequestMessage
    assert issubclass(CreateTodoBody, LegacyTodoBody)
    assert issubclass(AttachMediaPayload, LegacyAttachments)


@pytest.mark.parametrize("model", INPUT_MODELS)
def test_write_models_forbid_extras_and_coercion(model: type[BaseModel]) -> None:
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["strict"] is True
    assert model.model_config["validate_assignment"] is True
    assert model.model_config["revalidate_instances"] == "always"
    assert model.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize("name", ("create_todo", "create_todo_result"))
@pytest.mark.parametrize(
    ("content", "attachment", "expected"),
    [
        ("", None, {"content": ""}),
        ("  example  ", None, {"content": "  example  "}),
        ("example", {"upload_ids": []}, {"content": "example", "attachments": {"upload_ids": []}}),
        (
            "example",
            {"upload_ids": ["upload-test"]},
            {"content": "example", "attachments": {"upload_ids": ["upload-test"]}},
        ),
    ],
)
async def test_todo_wire_omission_and_empty_values(
    api: CasaApi,
    server: FakeServer,
    name: str,
    content: str,
    attachment: dict[str, Any] | None,
    expected: dict[str, Any],
) -> None:
    method, path, payload = operation(name)
    server.add(method, path, payload=payload)
    body = CreateTodoBody.model_validate({"content": content, "attachments": attachment})
    result = await invoke(api, name, body=body)
    if name == "create_todo_result":
        assert isinstance(result, CreateTodoResponse)
        assert result.needs_support_confirmation is True
    else:
        assert isinstance(result, TodoDetail)
    (call,) = server.calls(method, path)
    assert json.loads(call.body) == expected
    assert call.query == {}
    assert call.headers["Content-Type"] == "application/json"
    assert [(c.method, c.path) for c in server.seen] == [("POST", TOKEN_PATH), (method, path)]


@pytest.mark.parametrize("flag", [True, False])
async def test_create_todo_result_retains_flag_and_extras(
    api: CasaApi,
    server: FakeServer,
    flag: bool,
) -> None:
    server.add(
        "POST",
        f"{H}/todos",
        payload={
            "todo": TODO,
            "needs_support_confirmation": flag,
            "future_envelope": {"nested": None},
        },
    )
    result = await api.create_todo_result(HOME_ID, CreateTodoBody(content="example"))
    assert result.needs_support_confirmation is flag
    assert type(result.needs_support_confirmation) is bool
    assert result.model_extra == {"future_envelope": {"nested": None}}
    assert result.todo.model_extra == {"future_todo_field": {"nested": []}}
    assert len(server.seen) == 2


@pytest.mark.parametrize(
    "payload", [TODO, {"todo": TODO}, {"todo": TODO, "needs_support_confirmation": True}]
)
async def test_legacy_todo_response_compatibility(
    api: CasaApi,
    server: FakeServer,
    payload: dict[str, Any],
) -> None:
    server.add("POST", f"{H}/todos", payload=payload)
    result = await api.create_todo(HOME_ID, LegacyTodoBody(content="example"))
    assert type(result) is TodoDetail
    assert result.id == "todo-test"
    assert len(server.calls("POST", f"{H}/todos")) == 1


@pytest.mark.parametrize("name", ("create_todo", "create_todo_result"))
async def test_legacy_todo_attachment_input_compatibility(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, payload = operation(name)
    server.add(method, path, payload=payload)
    body = LegacyTodoBody(content="example", attachments=LegacyAttachments())
    await invoke(api, name, body=body)
    (call,) = server.calls(method, path)
    assert json.loads(call.body) == {"content": "example", "attachments": {"upload_ids": []}}


@pytest.mark.parametrize(
    "payload",
    [
        TODO,
        {},
        {"todo": TODO},
        {"todo": TODO, "needs_support_confirmation": None},
        *({"todo": TODO, "needs_support_confirmation": flag} for flag in INVALID_FLAGS),
        {"todo": None, "needs_support_confirmation": False},
        {"needs_support_confirmation": False},
        {"todo": {"id": "incomplete"}, "needs_support_confirmation": True},
    ],
)
async def test_create_todo_result_rejects_incomplete_or_coerced_response(
    api: CasaApi,
    server: FakeServer,
    payload: dict[str, Any],
) -> None:
    server.add("POST", f"{H}/todos", payload=payload)
    with pytest.raises(CasaResponseError, match="CreateTodoResponse"):
        await api.create_todo_result(HOME_ID, CreateTodoBody(content="example"))
    assert len(server.calls("POST", f"{H}/todos")) == 1


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, {}),
        ({"content": None, "attachments": None, "sender_role": None}, {}),
        ({"content": ""}, {"content": ""}),
        ({"content": "  example  "}, {"content": "  example  "}),
        ({"attachments": {"upload_ids": []}}, {"attachments": {"upload_ids": []}}),
        ({"sender_role": "member"}, {"sender_role": "member"}),
        (
            {
                "content": "",
                "attachments": {"upload_ids": ["upload-test"]},
                "sender_role": "member",
            },
            {
                "content": "",
                "attachments": {"upload_ids": ["upload-test"]},
                "sender_role": "member",
            },
        ),
    ],
)
async def test_message_wire_omission_and_empty_values(
    api: CasaApi,
    server: FakeServer,
    data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    path = f"{H}/requests/request-test/messages"
    server.add("POST", path, payload={"message": MESSAGE, "future_envelope": 1})
    result = await api.send_request_message(
        HOME_ID,
        "request-test",
        SendRequestMessageRequest.model_validate(data),
    )
    assert type(result.message) is RequestMessage
    assert result.message.id == "message-test"
    assert result.message.model_extra == {"future_message_field": {"nested": None}}
    assert result.message.attachments == MESSAGE["attachments"]
    assert result.model_extra == {"future_envelope": 1}
    (call,) = server.calls("POST", path)
    assert json.loads(call.body) == expected
    assert call.query == {}
    assert [(c.method, c.path) for c in server.seen] == [("POST", TOKEN_PATH), ("POST", path)]


@pytest.mark.parametrize("role", ["concierge", "vendor", "system", "unknown", "future-role"])
def test_privileged_roles_rejected_in_input_but_preserved_in_response(role: str) -> None:
    with pytest.raises(ValidationError):
        SendRequestMessageRequest.model_validate({"sender_role": role})
    message = {**MESSAGE, "sender_role": role}
    assert (
        SendRequestMessageResponse.model_validate({"message": message}).message.sender_role == role
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": None},
        MESSAGE,
        {"message": "not an object"},
        {"message": {"id": "incomplete"}},
    ],
)
async def test_send_message_requires_message_envelope(
    api: CasaApi,
    server: FakeServer,
    payload: dict[str, Any],
) -> None:
    path = f"{H}/requests/request-test/messages"
    server.add("POST", path, payload=payload)
    with pytest.raises(CasaResponseError, match="SendRequestMessageResponse"):
        await api.send_request_message(HOME_ID, "request-test", SendRequestMessageRequest())
    assert len(server.calls("POST", path)) == 1


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"props": []}, {"props": []}),
        ({"props": [], "make_id": None, "model_id": None}, {"props": []}),
        (
            {"props": [], "make_id": "", "model_id": ""},
            {"props": [], "make_id": "", "model_id": ""},
        ),
        (
            {
                "props": [
                    {
                        "definition_id": "definition-test",
                        "value": None,
                        "enum_id": None,
                        "multi_enums": None,
                    }
                ]
            },
            {"props": [{"definition_id": "definition-test"}]},
        ),
        (
            {
                "props": [
                    {
                        "definition_id": "definition-test",
                        "value": "",
                        "enum_id": "",
                        "multi_enums": [],
                    }
                ]
            },
            {
                "props": [
                    {
                        "definition_id": "definition-test",
                        "value": "",
                        "enum_id": "",
                        "multi_enums": [],
                    }
                ]
            },
        ),
        (
            {
                "make_id": "make-test",
                "model_id": "model-test",
                "props": [
                    {"definition_id": "text-test", "value": "  42  "},
                    {"definition_id": "enum-test", "enum_id": "enum-option-test"},
                    {
                        "definition_id": "multi-test",
                        "multi_enums": [
                            {"id": "selected-test", "is_selected": True},
                            {"id": "unselected-test", "is_selected": False},
                        ],
                    },
                ],
            },
            {
                "make_id": "make-test",
                "model_id": "model-test",
                "props": [
                    {"definition_id": "text-test", "value": "  42  "},
                    {"definition_id": "enum-test", "enum_id": "enum-option-test"},
                    {
                        "definition_id": "multi-test",
                        "multi_enums": [
                            {"id": "selected-test", "is_selected": True},
                            {"id": "unselected-test", "is_selected": False},
                        ],
                    },
                ],
            },
        ),
    ],
)
async def test_property_patch_wire_omission_and_explicit_values(
    api: CasaApi,
    server: FakeServer,
    data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    path = f"{MH}/entity/entity-test/props"
    server.add("PATCH", path, payload={"message": "", "future_envelope": {"nested": True}})
    result = await api.update_entity_properties(
        HOME_ID,
        "entity-test",
        UpdateEntityPropertiesRequest.model_validate(data),
    )
    assert type(result) is BasicMessageResponse
    assert result.message == ""
    assert result.model_extra == {"future_envelope": {"nested": True}}
    (call,) = server.calls("PATCH", path)
    assert json.loads(call.body) == expected
    assert call.query == {}
    assert [(c.method, c.path) for c in server.seen] == [("POST", TOKEN_PATH), ("PATCH", path)]


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": None}, {"message": 1}, {"message": False}, {"message": {}}, {"message": []}],
)
async def test_property_patch_requires_string_message(
    api: CasaApi,
    server: FakeServer,
    payload: dict[str, Any],
) -> None:
    path = f"{MH}/entity/entity-test/props"
    server.add("PATCH", path, payload=payload)
    with pytest.raises(CasaResponseError, match="BasicMessageResponse"):
        await api.update_entity_properties(
            HOME_ID, "entity-test", UpdateEntityPropertiesRequest(props=[])
        )
    assert len(server.calls("PATCH", path)) == 1


INVALID_BODIES: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (AttachMediaPayload, {}),
    (AttachMediaPayload, {"upload_ids": None}),
    (AttachMediaPayload, {"upload_ids": "upload-test"}),
    (AttachMediaPayload, {"upload_ids": [1]}),
    (AttachMediaPayload, {"upload_ids": [], "url": "https://example.invalid"}),
    (CreateTodoBody, {}),
    (CreateTodoBody, {"content": None}),
    (CreateTodoBody, {"content": 1}),
    (CreateTodoBody, {"content": "example", "sender_role": "system"}),
    (CreateTodoBody, {"content": "example", "attachments": {"upload_ids": [], "extra": None}}),
    (SendRequestMessageRequest, {"content": 1}),
    (SendRequestMessageRequest, {"attachments": []}),
    (SendRequestMessageRequest, {"attachments": {}}),
    (SendRequestMessageRequest, {"attachments": {"upload_ids": [False]}}),
    (SendRequestMessageRequest, {"attachments": {"upload_ids": [], "extra": None}}),
    (SendRequestMessageRequest, {"sender_role": 1}),
    (SendRequestMessageRequest, {"sender_role": ""}),
    (SendRequestMessageRequest, {"role": "system"}),
    (UpdateEntityPropertiesRequest, {}),
    (UpdateEntityPropertiesRequest, {"props": None}),
    (UpdateEntityPropertiesRequest, {"props": {}}),
    (UpdateEntityPropertiesRequest, {"props": ()}),
    (UpdateEntityPropertiesRequest, {"props": [], "make_id": 1}),
    (UpdateEntityPropertiesRequest, {"props": [], "model_id": 1}),
    (UpdateEntityPropertiesRequest, {"props": [], "extra": None}),
    (UpdateEntityPropertiesRequest, {"props": [{"definition_id": "d", "extra": None}]}),
    (UpdateEntityProperty, {}),
    (UpdateEntityProperty, {"definition_id": None}),
    (UpdateEntityProperty, {"definition_id": 1}),
    (UpdateEntityProperty, {"definition_id": "d", "value": 1}),
    (UpdateEntityProperty, {"definition_id": "d", "value": False}),
    (UpdateEntityProperty, {"definition_id": "d", "enum_id": 1}),
    (UpdateEntityProperty, {"definition_id": "d", "multi_enums": ["choice-test"]}),
    (UpdateEntityProperty, {"definition_id": "d", "multi_enums": [{"id": "choice-test"}]}),
    (
        UpdateEntityProperty,
        {
            "definition_id": "d",
            "multi_enums": [{"id": "choice-test", "is_selected": True, "extra": None}],
        },
    ),
    (UpdateMultiEnumProperty, {}),
    (UpdateMultiEnumProperty, {"id": "choice-test"}),
    (UpdateMultiEnumProperty, {"id": 1, "is_selected": True}),
    *[
        (UpdateMultiEnumProperty, {"id": "choice-test", "is_selected": value})
        for value in (None, 0, 1, "true", "false")
    ],
]


@pytest.mark.parametrize(("model", "data"), INVALID_BODIES)
def test_strict_input_validation(model: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("name", WRITE_METHODS)
@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        ".",
        "..",
        "x/y",
        "x\\y",
        "x?y",
        "x#y",
        "x%2Fy",
        "x y",
        "x\n",
        "x\x00",
        "x\x7f",
        "é",
        "x" * 2049,
        None,
        False,
        [],
        {},
    ],
)
async def test_home_ids_rejected_before_any_io(
    api: CasaApi,
    server: FakeServer,
    name: str,
    bad_id: Any,
) -> None:
    with pytest.raises(ValueError):
        await invoke(api, name, home_id=bad_id)
    assert server.seen == []


@pytest.mark.parametrize(
    ("name", "key"),
    [("send_request_message", "request_id"), ("update_entity_properties", "entity_id")],
)
@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        ".",
        "..",
        "x/y",
        "x\\y",
        "x?y",
        "x#y",
        "x%2Fy",
        "x y",
        "x\n",
        "x\x00",
        "x" * 2049,
        None,
        True,
        {},
    ],
)
async def test_resource_ids_rejected_before_any_io(
    api: CasaApi,
    server: FakeServer,
    name: str,
    key: str,
    bad_id: Any,
) -> None:
    with pytest.raises(ValueError):
        await invoke(api, name, **{key: bad_id})
    assert server.seen == []


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_safe_ids_forwarded_without_normalization(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    home_id = "HOME.Test_~-01"
    resource_id = "Resource.Test_~-02"
    method, original_path, payload = operation(name)
    path = (
        original_path.replace(HOME_ID, home_id)
        .replace("request-test", resource_id)
        .replace("entity-test", resource_id)
    )
    server.add(method, path, payload=payload)
    kwargs: dict[str, Any] = {"home_id": home_id}
    if name == "send_request_message":
        kwargs["request_id"] = resource_id
    elif name == "update_entity_properties":
        kwargs["entity_id"] = resource_id
    await invoke(api, name, **kwargs)
    assert len(server.calls(method, path)) == 1


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_body_bypass_attempts_revalidated_before_io(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    if name in {"create_todo", "create_todo_result"}:
        body: BaseModel = LegacyTodoBody.model_validate({"content": "example", "privileged": True})
    elif name == "send_request_message":
        body = SendRequestMessageRequest().model_copy(update={"sender_role": "system"})
    else:
        body = UpdateEntityPropertiesRequest(props=[UpdateEntityProperty(definition_id="d")])
        body.props[0].multi_enums = [UpdateMultiEnumProperty(id="choice-test", is_selected=True)]
        invalid_selection: dict[str, Any] = {"id": "choice-test", "is_selected": 1}
        body.props[0].multi_enums[0] = UpdateMultiEnumProperty.model_construct(**invalid_selection)
    with pytest.raises(CasaRequestError):
        await invoke(api, name, body=body)
    assert server.seen == []


@pytest.mark.parametrize("name", ("create_todo", "create_todo_result", "send_request_message"))
async def test_mutated_upload_lists_revalidated_before_io(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    attachments = AttachMediaPayload(upload_ids=[])
    body: CreateTodoBody | SendRequestMessageRequest = (
        CreateTodoBody(content="example", attachments=attachments)
        if name != "send_request_message"
        else SendRequestMessageRequest(attachments=attachments)
    )
    assert body.attachments is not None
    body.attachments.upload_ids.append(1)  # type: ignore[arg-type]
    with pytest.raises(CasaRequestError):
        await invoke(api, name, body=body)
    assert server.seen == []


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_writes_do_not_retry_server_failures(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, _ = operation(name)
    server.add(method, path, status=503, payload={"error": {"code": "synthetic_failure"}})
    with pytest.raises(CasaApiError):
        await invoke(api, name)
    assert len(server.calls(method, path)) == 1
    assert len(server.seen) == 2


@pytest.mark.parametrize(
    "name", ("create_todo_result", "send_request_message", "update_entity_properties")
)
async def test_schema_errors_sanitized_without_retry(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, _ = operation(name)
    payload: dict[str, Any]
    if name == "create_todo_result":
        payload = {
            "todo": {**deepcopy(TODO), "id": {"secret": CANARY}},
            "needs_support_confirmation": True,
        }
    elif name == "send_request_message":
        payload = {"message": {**deepcopy(MESSAGE), "id": {"secret": CANARY}}}
    else:
        payload = {"message": {"secret": CANARY}}
    server.add(method, path, payload=payload)
    with pytest.raises(CasaResponseError) as caught:
        await invoke(api, name)
    error = caught.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert CANARY not in str(error)
    assert CANARY not in repr(error)
    assert CANARY not in "".join(traceback.format_exception(error))
    assert len(server.calls(method, path)) == 1


@pytest.mark.parametrize("name", WRITE_METHODS)
@pytest.mark.parametrize("body", [None, {}, [], "example"])
async def test_nonmodel_body_rejected_before_io(
    api: CasaApi,
    server: FakeServer,
    name: str,
    body: Any,
) -> None:
    with pytest.raises(TypeError, match="request model"):
        await invoke(api, name, body=body)
    assert server.seen == []


@pytest.mark.parametrize("name", WRITE_METHODS)
@pytest.mark.parametrize("payload", [None, [], "example", False])
async def test_nonobject_response_rejected_without_retry(
    api: CasaApi,
    server: FakeServer,
    name: str,
    payload: Any,
) -> None:
    method, path, _ = operation(name)
    server.add(method, path, body=json.dumps(payload))
    with pytest.raises(CasaResponseError):
        await invoke(api, name)
    assert len(server.calls(method, path)) == 1


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_unknown_copied_write_field_rejected_before_io(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    if name in {"create_todo", "create_todo_result"}:
        body: BaseModel = CreateTodoBody(content="example")
    elif name == "send_request_message":
        body = SendRequestMessageRequest()
    else:
        body = UpdateEntityPropertiesRequest(props=[])
    body = body.model_copy(update={"future_write_field": None})
    with pytest.raises(CasaRequestError):
        await invoke(api, name, body=body)
    assert server.seen == []


def test_required_model_fields_have_no_defaults() -> None:
    for model, key in (
        (AttachMediaPayload, "upload_ids"),
        (CreateTodoBody, "content"),
        (CreateTodoResponse, "todo"),
        (CreateTodoResponse, "needs_support_confirmation"),
        (SendRequestMessageResponse, "message"),
        (UpdateEntityPropertiesRequest, "props"),
        (UpdateEntityProperty, "definition_id"),
        (UpdateMultiEnumProperty, "id"),
        (UpdateMultiEnumProperty, "is_selected"),
        (BasicMessageResponse, "message"),
    ):
        assert model.model_fields[key].is_required()


def test_strict_model_assignment_validation() -> None:
    message = SendRequestMessageRequest()
    with pytest.raises(ValidationError):
        message.sender_role = "system"  # type: ignore[assignment]
    assert message.sender_role is None
    choice = UpdateMultiEnumProperty(id="choice-test", is_selected=False)
    with pytest.raises(ValidationError):
        choice.is_selected = 1  # type: ignore[assignment]
    assert choice.is_selected is False


async def test_property_field_combinations_and_duplicates_not_invented_rules(
    api: CasaApi,
    server: FakeServer,
) -> None:
    path = f"{MH}/entity/entity-test/props"
    server.add("PATCH", path, payload={"message": "Synthetic status"})
    prop = UpdateEntityProperty(
        definition_id="definition-test",
        value="example",
        enum_id="choice-test",
        multi_enums=[],
    )
    await api.update_entity_properties(
        HOME_ID,
        "entity-test",
        UpdateEntityPropertiesRequest(props=[prop, prop]),
    )
    (call,) = server.calls("PATCH", path)
    assert json.loads(call.body) == {"props": [prop.model_dump(exclude_none=True)] * 2}


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_writes_never_retry_on_401(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    """A 401 after the server may have acted must not become a duplicate write."""
    method, path, payload = operation(name)
    server.add(method, path, status=401, payload={"error": "synthetic_expired_auth"})
    server.add(method, path, payload=payload)
    with pytest.raises(CasaAuthError):
        await invoke(api, name)
    assert len(server.calls(method, path)) == 1
    assert [(call.method, call.path) for call in server.seen] == [
        ("POST", TOKEN_PATH),
        (method, path),
    ]
    # The rejected token was dropped, so the next request refreshes first.
    assert api.client.auth._id_token is None


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_writes_force_refresh_token_before_sending(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, payload = operation(name)
    # The autouse fixture queued the first token. This one answers the forced refresh.
    server.add("POST", TOKEN_PATH, payload={**TOKEN, "id_token": "synthetic-fresh-id"})
    server.add(method, path, payload=payload)
    await api.client.auth.get_id_token()  # Cached and still valid.
    await invoke(api, name)
    (call,) = server.calls(method, path)
    assert call.headers["Authorization"] == "Bearer synthetic-fresh-id"
    assert [(seen.method, seen.path) for seen in server.seen] == [
        ("POST", TOKEN_PATH),
        ("POST", TOKEN_PATH),
        (method, path),
    ]


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_write_errors_drop_raw_body_fallback(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, _ = operation(name)
    server.add(method, path, status=500, body=f"<html>{CANARY}</html>")
    with pytest.raises(CasaApiError) as caught:
        await invoke(api, name)
    assert caught.value.display_message == ""
    assert CANARY not in str(caught.value)


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_write_non_json_success_drops_body(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, _ = operation(name)
    server.add(method, path, body=f"<html>{CANARY}</html>")
    with pytest.raises(CasaApiError) as caught:
        await invoke(api, name)
    assert caught.value.code == "invalid_json"
    assert CANARY not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_write_errors_keep_structured_envelope(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    method, path, _ = operation(name)
    envelope = {"code": "synthetic_code", "displayMessage": "Synthetic message"}
    server.add(method, path, status=400, payload={"error": envelope})
    with pytest.raises(CasaApiError) as caught:
        await invoke(api, name)
    assert (caught.value.code, caught.value.display_message) == (
        "synthetic_code",
        "Synthetic message",
    )


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_invalid_write_body_error_is_scrubbed(
    api: CasaApi,
    server: FakeServer,
    name: str,
) -> None:
    if name in {"create_todo", "create_todo_result"}:
        body: BaseModel = LegacyTodoBody.model_validate({"content": CANARY, "secret": CANARY})
    elif name == "send_request_message":
        body = SendRequestMessageRequest().model_copy(update={"sender_role": CANARY})
    else:
        body = UpdateEntityPropertiesRequest(props=[]).model_copy(update={"make_id": [CANARY]})
    with pytest.raises(CasaRequestError, match="validation error") as caught:
        await invoke(api, name, body=body)
    error = caught.value
    assert isinstance(error, ValueError)
    assert error.__cause__ is None and error.__context__ is None
    assert CANARY not in str(error)
    assert CANARY not in "".join(traceback.format_exception(error))
    assert server.seen == []


@pytest.mark.parametrize("name", WRITE_METHODS)
async def test_write_text_length_capped(api: CasaApi, server: FakeServer, name: str) -> None:
    limit = write_contracts.WRITE_TEXT_MAX_CHARS
    assert limit == 10_000
    method, path, payload = operation(name)
    server.add(method, path, payload=payload)

    def body(size: int) -> BaseModel:
        text = "x" * size
        if name in {"create_todo", "create_todo_result"}:
            return LegacyTodoBody(content=text)
        if name == "send_request_message":
            return SendRequestMessageRequest.model_construct(content=text)
        prop = UpdateEntityProperty.model_construct(definition_id="d", value=text)
        return UpdateEntityPropertiesRequest.model_construct(props=[prop])

    await invoke(api, name, body=body(limit))
    with pytest.raises(CasaRequestError):
        await invoke(api, name, body=body(limit + 1))
    assert len(server.calls(method, path)) == 1


def test_strict_models_reject_oversized_text_at_construction() -> None:
    oversized = "x" * (write_contracts.WRITE_TEXT_MAX_CHARS + 1)
    with pytest.raises(ValidationError):
        CreateTodoBody(content=oversized)
    with pytest.raises(ValidationError):
        SendRequestMessageRequest(content=oversized)
    with pytest.raises(ValidationError):
        UpdateEntityProperty(definition_id="d", value=oversized)
