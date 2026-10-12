"""Synthetic coverage of supplied traffic contracts. No live calls or private files.

Evidence markers come from the supplied contracts, never from these tests.
Reuse the loopback-only fake-server fixtures for every write and auth request.
"""

from __future__ import annotations

import inspect
import json
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
    CreateTodoBody,
    DocumentFileMetadataResponse,
    EntityModelName,
    SaveAndPublishEntityRequest,
    SaveAndPublishEntityResponse,
    TodoReadDetail,
    UpdateEntityProperty,
)
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer
from tests.test_static_reads import make_api
from tests.test_write_contracts import CANARY, TODO, TOKEN
from tests.test_write_contracts import loopback_only as loopback_only
from tests.test_write_contracts import synthetic_token as synthetic_token

H = f"/protected/home/{HOME_ID}"
MH = f"/protected/member/home/{HOME_ID}"
ENTITY_ID = "00000000-0000-4000-8000-000000000010"
DOCUMENT_ID = "00000000-0000-4000-8000-000000000011"
TODO_ID = "00000000-0000-4000-8000-000000000012"
PUBLISH_PATH = f"{MH}/entity/{ENTITY_ID}/save_and_publish"
PUBLISHED: dict[str, Any] = {
    "entity_id": ENTITY_ID,
    "status": "published",
    "make": {"id": "make-test", "name": "Example make"},
    "model": {"id": "model-test", "name": "Example model"},
    "identity": {
        "state": "verified",
        "unverified_make": None,
        "unverified_model": None,
        "candidates": [],
    },
}
CITATION = {"page_index": 0, "page_label": "1", "excerpt": "Synthetic excerpt"}
SUGGESTION: dict[str, Any] = {
    "id": "suggestion-test",
    "todo_id": TODO_ID,
    "title": "Synthetic suggestion",
    "action": "Synthetic action",
    "reason": "Synthetic reason",
    "area": "Synthetic area",
    "citations": [CITATION],
    "state": "pending",
    "work_deleted": False,
    "matches": [],
    "task_id": None,
    "request_id": None,
}
STRUCTURE: dict[str, Any] = {
    "id": "structure-test",
    "entity_id": ENTITY_ID,
    "definition_id": "definition-test",
    "section": "Synthetic section",
    "title": "Synthetic title",
    "current_values": ["Synthetic value"],
    "current_label": "Synthetic current",
    "proposed_label": "Synthetic proposed",
    "reason": "Synthetic reason",
    "state": "pending",
    "changed_since_analysis": False,
    "responded_at": None,
    "citations": [CITATION],
}


async def publish(api: CasaApi, name: str, **overrides: Any) -> SaveAndPublishEntityResponse:
    kwargs: dict[str, Any] = {"home_id": HOME_ID, "entity_id": ENTITY_ID}
    if name == "update_entity_model":
        kwargs["model_name"] = "  Example model  "
    else:
        kwargs["body"] = SaveAndPublishEntityRequest(
            model=EntityModelName(name="  Example model  "), props=[]
        )
    kwargs.update(overrides)
    result: SaveAndPublishEntityResponse = await getattr(api, name)(**kwargs)
    return result


@pytest.mark.parametrize("name", ["save_and_publish_entity", "update_entity_model"])
async def test_publish_wire_and_typed_result(api: CasaApi, server: FakeServer, name: str) -> None:
    server.add("POST", PUBLISH_PATH, payload={**PUBLISHED, "future_field": [None]})
    result = await publish(api, name)
    assert isinstance(result, SaveAndPublishEntityResponse)
    assert result.entity_id == ENTITY_ID
    assert result.status == "published"
    assert result.make.name == "Example make"
    assert result.model.name == "Example model"
    assert result.identity.state == "verified"
    assert result.identity.candidates == []
    assert result.model_extra == {"future_field": [None]}
    (call,) = server.calls("POST", PUBLISH_PATH)
    assert json.loads(call.body) == {"model": {"name": "  Example model  "}, "props": []}
    assert call.query == {}
    assert [(c.method, c.path) for c in server.seen] == [
        ("POST", TOKEN_PATH),
        ("POST", PUBLISH_PATH),
    ]


@pytest.mark.parametrize("name", ["save_and_publish_entity", "update_entity_model", "delete_todo"])
@pytest.mark.parametrize("status", [401, 503])
async def test_new_writes_sent_once_on_failure(
    api: CasaApi, server: FakeServer, name: str, status: int
) -> None:
    method = "DELETE" if name == "delete_todo" else "POST"
    path = f"{H}/todos/{TODO_ID}" if name == "delete_todo" else PUBLISH_PATH
    server.add(method, path, status=status, body=f"<html>{CANARY}</html>")
    server.add(method, path, payload=PUBLISHED)
    error = CasaAuthError if status == 401 else CasaApiError
    with pytest.raises(error) as caught:
        if name == "delete_todo":
            await api.delete_todo(HOME_ID, TODO_ID)
        else:
            await publish(api, name)
    assert CANARY not in str(caught.value)
    assert len(server.calls(method, path)) == 1
    assert len(server.seen) == 2


@pytest.mark.parametrize("name", ["save_and_publish_entity", "update_entity_model", "delete_todo"])
async def test_new_writes_force_refresh_first(api: CasaApi, server: FakeServer, name: str) -> None:
    server.add("POST", TOKEN_PATH, payload={**TOKEN, "id_token": "synthetic-fresh-id"})
    await api.client.auth.get_id_token()
    method = "DELETE" if name == "delete_todo" else "POST"
    path = f"{H}/todos/{TODO_ID}" if name == "delete_todo" else PUBLISH_PATH
    server.add(method, path, status=204 if method == "DELETE" else 200, payload=PUBLISHED)
    if name == "delete_todo":
        await api.delete_todo(HOME_ID, TODO_ID)
    else:
        await publish(api, name)
    (call,) = server.calls(method, path)
    assert call.headers["Authorization"] == "Bearer synthetic-fresh-id"
    assert len(server.calls("POST", TOKEN_PATH)) == 2


async def test_delete_is_bodyless_204(api: CasaApi, server: FakeServer) -> None:
    path = f"{H}/todos/{TODO_ID}"
    server.add("DELETE", path, status=204)
    await api.delete_todo(HOME_ID, TODO_ID)
    (call,) = server.calls("DELETE", path)
    assert call.body == ""
    assert call.query == {}
    assert call.headers.get("Content-Type") != "application/json"


@pytest.mark.parametrize("name", ["save_and_publish_entity", "update_entity_model", "delete_todo"])
@pytest.mark.parametrize("key", ["home_id", "resource_id"])
@pytest.mark.parametrize("bad", ["", "..", "x/y", "x?y", "x%2fy", "x\n", True, None, {}, 1.5])
async def test_new_write_ids_validated_before_io(
    api: CasaApi, server: FakeServer, name: str, key: str, bad: Any
) -> None:
    kwargs = {"home_id" if key == "home_id" else "entity_id": bad}
    with pytest.raises(CasaRequestError) as caught:
        if name == "delete_todo":
            await api.delete_todo(
                bad if key == "home_id" else HOME_ID, bad if key == "resource_id" else TODO_ID
            )
        else:
            await publish(api, name, **kwargs)
    assert caught.value.__context__ is None
    assert server.seen == []


@pytest.mark.parametrize("model", [EntityModelName, SaveAndPublishEntityRequest])
def test_publish_input_models_strict_and_exported(model: type[BaseModel]) -> None:
    assert model.model_config["strict"] is True
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["validate_assignment"] is True
    assert model.model_config["revalidate_instances"] == "always"
    assert getattr(models, model.__name__) is model
    assert model.__name__ in models.__all__


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"model": {"name": "Example"}},
        {"model": {"name": 7}, "props": []},
        {"model": {"name": "Example", "id": "model-test"}, "props": []},
        {"make": {"id": "make-test", "name": "Example"}, "props": []},
        {"make": {}, "props": []},
        {"make": None, "model": None, "props": []},
        {"props": []},
        {"make": {"clear": True}, "props": []},
        {"make": "make-test", "props": []},
        {"model": {"name": ""}, "props": []},
        {"model": {"name": "   "}, "props": []},
        {"model": {"name": "a\nb"}, "props": []},
        {"model": {"name": "x" * 257}, "props": []},
        {"model": {"id": ""}, "props": []},
        {"model": {"id": "a/b"}, "props": []},
        {"model": {"id": "x" * 129}, "props": []},
        {"model": {"id": 7}, "props": []},
        {"model": {"name": "Example"}, "props": [{"definition_id": "test", "value": "x"}]},
        {"model": {"name": "Example"}, "props": ()},
        {"model": None, "props": []},
        {"model": {"name": None}, "props": []},
    ],
)
def test_publish_does_not_invent_variants(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SaveAndPublishEntityRequest.model_validate(body)


@pytest.mark.parametrize("bad", [None, True, 12, [CANARY], "x" * 10_001])
async def test_model_name_invalid_inputs_scrubbed_before_io(
    api: CasaApi, server: FakeServer, bad: Any
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await api.update_entity_model(HOME_ID, ENTITY_ID, bad)
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert server.seen == []


@pytest.mark.parametrize("mutation", ["props", "name", "extra"])
async def test_copied_and_mutated_publish_body_revalidated(
    api: CasaApi, server: FakeServer, mutation: str
) -> None:
    body = SaveAndPublishEntityRequest(model=EntityModelName(name="Example"), props=[])
    if mutation == "props":
        body.props.append(UpdateEntityProperty(definition_id="test", value=CANARY))
    elif mutation == "name":
        assert body.model is not None
        body = body.model_copy(update={"model": body.model.model_copy(update={"name": [CANARY]})})
    else:
        body = body.model_copy(update={"make": CANARY})
    with pytest.raises(CasaRequestError) as caught:
        await api.save_and_publish_entity(HOME_ID, ENTITY_ID, body)
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert server.seen == []


@pytest.mark.parametrize("name", ["save_and_publish_entity", "update_entity_model"])
@pytest.mark.parametrize("missing", ["entity_id", "status", "make", "model", "identity"])
async def test_publish_response_required_fields_no_retry(
    api: CasaApi, server: FakeServer, name: str, missing: str
) -> None:
    payload = deepcopy(PUBLISHED)
    del payload[missing]
    server.add("POST", PUBLISH_PATH, payload=payload)
    with pytest.raises(CasaResponseError):
        await publish(api, name)
    assert len(server.calls("POST", PUBLISH_PATH)) == 1


async def test_publish_response_error_scrubbed(api: CasaApi, server: FakeServer) -> None:
    server.add("POST", PUBLISH_PATH, payload={**PUBLISHED, "model": {"name": {"secret": CANARY}}})
    with pytest.raises(CasaResponseError) as caught:
        await api.update_entity_model(HOME_ID, ENTITY_ID, "Example")
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert len(server.calls("POST", PUBLISH_PATH)) == 1


@pytest.mark.parametrize("state", ["pending", "accepted", "future-state"])
async def test_populated_document_suggestions_and_future_matches(state: str) -> None:
    future_match = {"future_match": [None, "Synthetic value"]}
    api, client = make_api(
        {
            "suggestions": [{**SUGGESTION, "state": state, "matches": [future_match]}],
            "next_cursor": None,
            "analysis_status": "completed",
            "limitations": [],
        }
    )
    result = await api.document_suggestions(HOME_ID, DOCUMENT_ID)
    item = result.suggestions[0]
    assert item.state == state
    assert item.todo_id == TODO_ID
    assert item.matches == [future_match]
    assert item.citations[0].page_label == "1"
    assert result.next_cursor is None
    assert client.calls == [(f"{H}/documents/{DOCUMENT_ID}/suggestions", {})]


@pytest.mark.parametrize("view", [None, "all", "", "synthetic/view+=?&#", "  Synthetic view  "])
async def test_suggestion_view_omission_and_preservation(
    api: CasaApi, server: FakeServer, view: str | None
) -> None:
    path = f"{H}/documents/{DOCUMENT_ID}/suggestions"
    server.add(
        "GET",
        path,
        payload={
            "suggestions": [SUGGESTION],
            "next_cursor": None,
            "analysis_status": "completed",
            "limitations": [],
        },
    )
    await api.document_suggestions(HOME_ID, DOCUMENT_ID, view=view)
    (call,) = server.calls("GET", path)
    assert call.query == ({} if view is None else {"view": view})


@pytest.mark.parametrize("bad", [False, 1, [], {}, "a\n", "a\x00", "a\x85", "x" * 2049])
async def test_invalid_view_rejected_before_io(bad: Any) -> None:
    api, client = make_api({})
    with pytest.raises(ValueError):
        await api.document_suggestions(HOME_ID, DOCUMENT_ID, view=bad)
    assert client.calls == []


@pytest.mark.parametrize(
    "state,responded_at", [("pending", None), ("accepted", 20), ("future-state", 21)]
)
async def test_populated_structure_metadata(state: str, responded_at: int | None) -> None:
    api, client = make_api(
        {"suggestions": [{**STRUCTURE, "state": state, "responded_at": responded_at}]}
    )
    result = await api.document_structure_suggestions(HOME_ID, DOCUMENT_ID)
    item = result.suggestions[0]
    assert item.entity_id == ENTITY_ID
    assert item.definition_id == "definition-test"
    assert item.current_values == ["Synthetic value"]
    assert item.responded_at == responded_at
    assert item.state == state
    assert item.citations[0].excerpt == "Synthetic excerpt"
    assert len(client.calls) == 1


async def test_file_metadata_typed_and_never_downloaded() -> None:
    url = "https://example.invalid/synthetic-document?signature=synthetic"
    api, client = make_api({"url": url, "expires_at": 20, "future_field": []})
    result = await api.document_file_metadata(HOME_ID, DOCUMENT_ID)
    assert type(result) is DocumentFileMetadataResponse
    assert result.url == url and result.expires_at == 20
    assert result.model_extra == {"future_field": []}
    assert client.calls == [(f"{H}/documents/{DOCUMENT_ID}/file", {})]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"url": "https://example.invalid"},
        {"url": "https://example.invalid", "expires_at": "20"},
        {"url": "https://example.invalid", "expires_at": True},
        {"url": {"secret": CANARY}, "expires_at": 20},
    ],
)
async def test_file_metadata_schema_errors_scrubbed(payload: dict[str, Any]) -> None:
    api, client = make_api(payload)
    with pytest.raises(CasaResponseError) as caught:
        await api.document_file_metadata(HOME_ID, DOCUMENT_ID)
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "name", ["document_file_metadata", "document_suggestions", "document_structure_suggestions"]
)
@pytest.mark.parametrize("key", ["home_id", "document_id"])
@pytest.mark.parametrize("bad", ["", "..", "x/y", "x?y", "x%2Fy", "x\n", None, True])
async def test_document_path_inputs_validated_before_io(name: str, key: str, bad: Any) -> None:
    api, client = make_api({})
    args = {"home_id": HOME_ID, "document_id": DOCUMENT_ID, key: bad}
    with pytest.raises(ValueError):
        await getattr(api, name)(**args)
    assert client.calls == []


@pytest.mark.parametrize("name", ["create_todo", "create_todo_result"])
async def test_plain_text_creation_observed_envelope(
    api: CasaApi, server: FakeServer, name: str
) -> None:
    todo = {
        **TODO,
        "source_document_id": DOCUMENT_ID,
        "suggestion_response_reason": None,
        "question_rounds": [
            {
                "id": "round-test",
                "state": "future-state",
                "questions": [{"future_question": [None, "Synthetic"]}],
            }
        ],
    }
    server.add(
        "POST",
        f"{H}/todos",
        status=201,
        payload={"todo": todo, "needs_support_confirmation": False},
    )
    result = await getattr(api, name)(HOME_ID, CreateTodoBody(content="Synthetic input"))
    detail = result.todo if name == "create_todo_result" else result
    assert detail.source_document_id == DOCUMENT_ID
    assert detail.suggestion_response_reason is None
    assert detail.question_rounds == todo["question_rounds"]
    if name == "create_todo_result":
        assert result.needs_support_confirmation is False
    (call,) = server.calls("POST", f"{H}/todos")
    assert json.loads(call.body) == {"content": "Synthetic input"}
    typed = TodoReadDetail.model_validate(todo)
    assert typed.source_document_id == DOCUMENT_ID
    assert typed.question_rounds[0].questions == [{"future_question": [None, "Synthetic"]}]


@pytest.mark.parametrize(
    "name,response",
    [
        ("save_and_publish_entity", SaveAndPublishEntityResponse),
        ("update_entity_model", SaveAndPublishEntityResponse),
        ("delete_todo", type(None)),
        ("document_file_metadata", DocumentFileMetadataResponse),
    ],
)
def test_interface_annotations_and_evidence(name: str, response: type[Any]) -> None:
    method = getattr(CasaApi, name)
    assert inspect.iscoroutinefunction(method)
    assert get_type_hints(method)["return"] is response
    assert get_type_hints(method)["home_id"] is str
    assert not is_unverified(method)
    assert (method.__doc__ or "").startswith("VERIFIED")


def test_narrow_confidence_caveats() -> None:
    assert "UNVERIFIED" in (CasaApi.save_and_publish_entity.__doc__ or "")
    assert "UNVERIFIED" in (CasaApi.update_entity_model.__doc__ or "")
    assert 'value "all" were observed' in (CasaApi.document_suggestions.__doc__ or "")
    assert "Other values" in (CasaApi.document_suggestions.__doc__ or "")
    assert is_unverified(CasaApi.update_entity_properties)
    # Its encoder is now reconstructed, not confirmed by a live edit.
    assert is_unverified(CasaApi.update_document)
