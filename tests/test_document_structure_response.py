"""Synthetic accepted-only structure response contract. No live calls or private data."""

from __future__ import annotations

import inspect
import json
import traceback
from collections.abc import Sequence
from typing import Any, Literal, get_type_hints

import pytest
from pydantic import ValidationError

from casahome import (
    CasaApi,
    CasaApiError,
    CasaAuthError,
    CasaRequestError,
    CasaResponseError,
    is_unverified,
    models,
)
from casahome.models import RespondToDocumentStructureSuggestionRequest, SavedResponse
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer
from tests.test_write_contracts import CANARY, TOKEN
from tests.test_write_contracts import loopback_only as loopback_only
from tests.test_write_contracts import synthetic_token as synthetic_token

DOCUMENT_ID = "00000000-0000-4000-8000-000000000020"
SUGGESTION_ID = "00000000-0000-4000-8000-000000000021"
PATH = (
    f"/protected/home/{HOME_ID}/documents/{DOCUMENT_ID}"
    f"/structure_suggestions/{SUGGESTION_ID}/respond"
)


@pytest.mark.parametrize("values", [[], [""], ["  Example  ", "x", "x"], ("Example", "other")])
@pytest.mark.parametrize("explicit_decision", [False, True])
async def test_accepted_wire_required_guard_and_no_followup(
    api: CasaApi, server: FakeServer, values: Sequence[str], explicit_decision: bool
) -> None:
    server.add("POST", PATH, payload={"saved": True, "future_field": []})
    if explicit_decision:
        result = await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, values, "accepted"
        )
    else:
        result = await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, values
        )
    assert type(result) is SavedResponse
    assert result.saved is True
    assert result.model_extra == {"future_field": []}
    (call,) = server.calls("POST", PATH)
    assert json.loads(call.body) == {"decision": "accepted", "expected_values": list(values)}
    assert call.query == {}
    assert call.headers["Content-Type"] == "application/json"
    assert "Idempotency-Key" not in call.headers
    assert [(c.method, c.path) for c in server.seen] == [("POST", TOKEN_PATH), ("POST", PATH)]


@pytest.mark.parametrize("decision", ["accept", "future-decision", "", None, True, 1])
async def test_only_accepted_decision_allowed_before_io(
    api: CasaApi, server: FakeServer, decision: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, ["Example"], decision
        )
    assert server.seen == []


@pytest.mark.parametrize(
    "values", [None, "Example", b"Example", {}, {"Example"}, 1, False, [1], [None], [False]]
)
async def test_guard_rejects_nonsequences_and_coercion_before_io(
    api: CasaApi, server: FakeServer, values: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, values
        )
    assert server.seen == []


@pytest.mark.parametrize("key", ["home_id", "document_id", "suggestion_id"])
@pytest.mark.parametrize("bad", ["", "..", "x/y", "x?y", "x#y", "x%2fy", "x\n", True, None, {}])
async def test_response_ids_validated_before_io(
    api: CasaApi, server: FakeServer, key: str, bad: Any
) -> None:
    kwargs: dict[str, Any] = {
        "home_id": HOME_ID,
        "document_id": DOCUMENT_ID,
        "suggestion_id": SUGGESTION_ID,
        "expected_values": ["Example"],
        key: bad,
    }
    with pytest.raises(CasaRequestError):
        await api.respond_to_document_structure_suggestion(**kwargs)
    assert server.seen == []


@pytest.mark.parametrize("status", [401, 409, 503])
async def test_structure_response_never_retries_or_refreshes_guard(
    api: CasaApi, server: FakeServer, status: int
) -> None:
    server.add("POST", PATH, status=status, body=f"<html>{CANARY}</html>")
    server.add("POST", PATH, payload={"saved": True})
    error = CasaAuthError if status == 401 else CasaApiError
    with pytest.raises(error) as caught:
        await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, ["Example"]
        )
    assert CANARY not in str(caught.value)
    assert [(c.method, c.path) for c in server.seen] == [("POST", TOKEN_PATH), ("POST", PATH)]


async def test_structure_response_refreshes_auth_before_write(
    api: CasaApi, server: FakeServer
) -> None:
    server.add("POST", TOKEN_PATH, payload={**TOKEN, "id_token": "synthetic-fresh-id"})
    await api.client.auth.get_id_token()
    server.add("POST", PATH, payload={"saved": True})
    await api.respond_to_document_structure_suggestion(
        HOME_ID, DOCUMENT_ID, SUGGESTION_ID, ["Example"]
    )
    (call,) = server.calls("POST", PATH)
    assert call.headers["Authorization"] == "Bearer synthetic-fresh-id"
    assert len(server.calls("POST", TOKEN_PATH)) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"saved": None},
        {"saved": 0},
        {"saved": 1},
        {"saved": "true"},
        {"saved": []},
        {"saved": {"secret": CANARY}},
        None,
        [],
        True,
    ],
)
async def test_saved_response_requires_strict_boolean_and_scrubs_errors(
    api: CasaApi, server: FakeServer, payload: Any
) -> None:
    server.add("POST", PATH, body=json.dumps(payload))
    with pytest.raises(CasaResponseError) as caught:
        await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, ["Example"]
        )
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert len(server.calls("POST", PATH)) == 1


async def test_false_is_preserved_without_implying_observed_success(
    api: CasaApi, server: FakeServer
) -> None:
    server.add("POST", PATH, payload={"saved": False})
    result = await api.respond_to_document_structure_suggestion(
        HOME_ID, DOCUMENT_ID, SUGGESTION_ID, ["Example"]
    )
    assert result.saved is False
    assert "UNVERIFIED" in (SavedResponse.__doc__ or "")
    assert len(server.calls("POST", PATH)) == 1


def test_exact_signature_requires_expected_values() -> None:
    method = CasaApi.respond_to_document_structure_suggestion
    signature = inspect.signature(method)
    assert list(signature.parameters) == [
        "self",
        "home_id",
        "document_id",
        "suggestion_id",
        "expected_values",
        "decision",
    ]
    assert signature.parameters["expected_values"].default is inspect.Parameter.empty
    assert signature.parameters["decision"].default == "accepted"
    hints = get_type_hints(method)
    assert hints["expected_values"] == Sequence[str]
    assert hints["decision"] == Literal["accepted"]
    assert hints["return"] is SavedResponse
    assert not is_unverified(method)
    assert (method.__doc__ or "").startswith("VERIFIED")


@pytest.mark.parametrize(
    "data",
    [
        {"decision": "accepted"},
        {"expected_values": []},
        {"decision": "accept", "expected_values": []},
        {"decision": "accepted", "expected_values": ("Example",)},
        {"decision": "accepted", "expected_values": [], "extra": None},
    ],
)
def test_strict_request_schema_and_required_fields(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RespondToDocumentStructureSuggestionRequest.model_validate(data)


def test_models_exported_without_permissive_request_config() -> None:
    model = RespondToDocumentStructureSuggestionRequest
    assert model.model_config["strict"] is True
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["validate_assignment"] is True
    assert model.model_config["revalidate_instances"] == "always"
    for key in ("decision", "expected_values"):
        assert model.model_fields[key].is_required()
    assert SavedResponse.model_fields["saved"].is_required()
    for exported in (model, SavedResponse):
        assert getattr(models, exported.__name__) is exported
        assert exported.__name__ in models.__all__


async def test_invalid_guard_error_drops_private_input(api: CasaApi, server: FakeServer) -> None:
    invalid: Any = [{"secret": CANARY}]
    with pytest.raises(CasaRequestError) as caught:
        await api.respond_to_document_structure_suggestion(
            HOME_ID, DOCUMENT_ID, SUGGESTION_ID, invalid
        )
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert server.seen == []
