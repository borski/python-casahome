"""Make/model catalog selections, room rename and snake_case API errors.

Synthetic data only, against the loopback FakeServer. Contracts come from a
private capture analyzed elsewhere (2026-10). Nothing here reads it.
"""

from __future__ import annotations

import inspect
import json
import traceback
from typing import Any

import pytest
from pydantic import ValidationError

from casahome import CasaApi, CasaApiError, CasaAuthError, CasaRequestError
from casahome.client import _api_error
from casahome.models import (
    BasicMessageResponse,
    CatalogFieldId,
    CatalogFieldName,
    EntityModelName,
    RenameRoomRequest,
    SaveAndPublishEntityRequest,
)
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer
from tests.test_observed_contracts import ENTITY_ID, PUBLISH_PATH, PUBLISHED
from tests.test_write_contracts import CANARY
from tests.test_write_contracts import loopback_only as loopback_only
from tests.test_write_contracts import synthetic_token as synthetic_token

ROOM_ID = "00000000-0000-4000-8000-000000000020"
ROOM_TYPE_ID = "00000000-0000-4000-8000-000000000021"
ROOM_PATH = f"/protected/member/home/{HOME_ID}/room/{ROOM_ID}"
UNVERIFIED_ERROR = {
    "error": {
        "code": "CATALOG_MODEL_UNVERIFIED",
        "display_title": "Couldn't find this product",
        "display_message": "Synthetic display message",
        "request_id": "req-synthetic",
    }
}


# Error parsing ------------------------------------------------------------------


def test_api_error_accepts_snake_case_fields() -> None:
    err = _api_error(400, json.dumps(UNVERIFIED_ERROR))
    assert (err.status, err.code, err.display_title, err.display_message, err.request_id) == (
        400,
        "CATALOG_MODEL_UNVERIFIED",
        "Couldn't find this product",
        "Synthetic display message",
        "req-synthetic",
    )


def test_api_error_accepts_camel_case_fields() -> None:
    body = {
        "error": {
            "code": "not_found",
            "displayTitle": "Title",
            "displayMessage": "Message",
            "requestId": "req-camel",
        }
    }
    err = _api_error(404, json.dumps(body))
    assert (err.code, err.display_title, err.display_message, err.request_id) == (
        "not_found",
        "Title",
        "Message",
        "req-camel",
    )


def test_api_error_prefers_camel_case_when_both_present() -> None:
    body = {"error": {"code": "x", "displayTitle": "camel", "display_title": "snake"}}
    assert _api_error(400, json.dumps(body)).display_title == "camel"


def test_api_error_missing_fields_default_empty() -> None:
    err = _api_error(400, json.dumps({"error": {"code": "x"}}))
    assert (err.display_title, err.display_message, err.request_id) == ("", "", "")


# Make/model selections ----------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,body",
    [
        ({"model_name": "Example"}, {"model": {"name": "Example"}, "props": []}),
        ({"model_id": "model-1"}, {"model": {"id": "model-1"}, "props": []}),
        ({"make_id": "make-1"}, {"make": {"id": "make-1"}, "props": []}),
        ({"make_name": "Example"}, {"make": {"name": "Example"}, "props": []}),
        (
            {"make_id": "make-1", "model_name": "  Padded  "},
            {"make": {"id": "make-1"}, "model": {"name": "  Padded  "}, "props": []},
        ),
        (
            {"make_name": "Make", "model_name": "Model"},
            {"make": {"name": "Make"}, "model": {"name": "Model"}, "props": []},
        ),
    ],
)
async def test_make_model_wire_body(
    api: CasaApi, server: FakeServer, kwargs: dict[str, str], body: dict[str, Any]
) -> None:
    server.add("POST", PUBLISH_PATH, payload=PUBLISHED)
    result = await api.update_entity_make_model(HOME_ID, ENTITY_ID, **kwargs)
    assert result.status == "published"
    assert result.identity.unverified_make is None
    (call,) = server.calls("POST", PUBLISH_PATH)
    assert json.loads(call.body) == body


async def test_save_and_publish_accepts_typed_selections(api: CasaApi, server: FakeServer) -> None:
    server.add("POST", PUBLISH_PATH, payload=PUBLISHED)
    body = SaveAndPublishEntityRequest(
        make=CatalogFieldId(id="make-1"), model=CatalogFieldName(name="Example"), props=[]
    )
    await api.save_and_publish_entity(HOME_ID, ENTITY_ID, body)
    (call,) = server.calls("POST", PUBLISH_PATH)
    assert json.loads(call.body) == {
        "make": {"id": "make-1"},
        "model": {"name": "Example"},
        "props": [],
    }


def test_entity_model_name_still_accepted() -> None:
    body = SaveAndPublishEntityRequest(model=EntityModelName(name="Example"), props=[])
    assert body.model_dump(exclude_none=True) == {"model": {"name": "Example"}, "props": []}


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"make_id": "make-1", "make_name": "Make"},
        {"model_id": "model-1", "model_name": "Model"},
        {"make_id": "make-1", "make_name": "Make", "model_name": "Model"},
        {"model_name": ""},
        {"model_name": "   "},
        {"model_name": f"{CANARY}\n"},
        {"model_name": "x" * 257},
        {"model_id": "a/b"},
        {"model_id": ""},
        {"make_id": True},
        {"make_name": [CANARY]},
    ],
)
async def test_make_model_rejected_before_io(
    api: CasaApi, server: FakeServer, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await api.update_entity_make_model(HOME_ID, ENTITY_ID, **kwargs)
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert server.seen == []


@pytest.mark.parametrize("name", ["update_entity_make_model", "rename_room"])
def test_selection_args_are_keyword_only(name: str) -> None:
    params = inspect.signature(getattr(CasaApi, name)).parameters.values()
    keyword_only = {p.name for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY}
    expected = (
        {"make_id", "make_name", "model_id", "model_name"}
        if name == "update_entity_make_model"
        else {"room_type_id", "name"}
    )
    assert keyword_only == expected


async def test_unknown_product_raises_specific_code_once(api: CasaApi, server: FakeServer) -> None:
    server.add("POST", PUBLISH_PATH, status=400, payload=UNVERIFIED_ERROR)
    with pytest.raises(CasaApiError) as caught:
        await api.update_entity_make_model(
            HOME_ID, ENTITY_ID, make_name="Unknown", model_name="Unknown"
        )
    assert caught.value.status == 400
    assert caught.value.code == "CATALOG_MODEL_UNVERIFIED"
    assert caught.value.display_title == "Couldn't find this product"
    assert len(server.calls("POST", PUBLISH_PATH)) == 1


def test_selection_union_rejects_both_keys() -> None:
    with pytest.raises(ValidationError):
        SaveAndPublishEntityRequest.model_validate(
            {"make": {"id": "make-1", "name": "Make"}, "props": []}
        )


# Room rename --------------------------------------------------------------------


async def test_rename_room_wire(api: CasaApi, server: FakeServer) -> None:
    server.add("PATCH", ROOM_PATH, payload={"message": "Room updated"})
    result = await api.rename_room(HOME_ID, ROOM_ID, room_type_id=ROOM_TYPE_ID, name="Dobby Area")
    assert isinstance(result, BasicMessageResponse)
    assert result.message == "Room updated"
    (call,) = server.calls("PATCH", ROOM_PATH)
    assert json.loads(call.body) == {"room_type_id": ROOM_TYPE_ID, "name": "Dobby Area"}
    assert call.query == {}
    assert [(c.method, c.path) for c in server.seen] == [
        ("POST", TOKEN_PATH),
        ("PATCH", ROOM_PATH),
    ]


async def test_rename_room_401_not_retried(api: CasaApi, server: FakeServer) -> None:
    server.add("PATCH", ROOM_PATH, status=401, payload={"error": "synthetic"})
    server.add("PATCH", ROOM_PATH, payload={"message": "Room updated"})
    with pytest.raises(CasaAuthError):
        await api.rename_room(HOME_ID, ROOM_ID, room_type_id=ROOM_TYPE_ID, name="Room")
    assert len(server.calls("PATCH", ROOM_PATH)) == 1


@pytest.mark.parametrize(
    "room_type_id,name",
    [
        ("", "Room"),
        ("a/b", "Room"),
        (None, "Room"),
        (ROOM_TYPE_ID, ""),
        (ROOM_TYPE_ID, "  "),
        (ROOM_TYPE_ID, f"{CANARY}\x00"),
        (ROOM_TYPE_ID, "x" * 257),
        (ROOM_TYPE_ID, None),
        (ROOM_TYPE_ID, 7),
    ],
)
async def test_rename_room_rejected_before_io(
    api: CasaApi, server: FakeServer, room_type_id: Any, name: Any
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await api.rename_room(HOME_ID, ROOM_ID, room_type_id=room_type_id, name=name)
    assert caught.value.__context__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert server.seen == []


def test_rename_room_body_is_strict() -> None:
    assert RenameRoomRequest.model_config["extra"] == "forbid"
    with pytest.raises(ValidationError):
        RenameRoomRequest.model_validate({"name": "Room"})
    with pytest.raises(ValidationError):
        RenameRoomRequest.model_validate({"room_type_id": ROOM_TYPE_ID, "name": "Room", "floor": 1})
