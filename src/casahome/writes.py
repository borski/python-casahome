"""Writes VERIFIED against live app traffic (2026-10).

Each method's docstring records what was observed: method, path, request body
and response. ``CasaApi`` inherits these, so call them as ``api.method(...)``.

Every write is sent once. The ID token is force-refreshed first and an HTTP 401
raises ``CasaAuthError`` without a retry, since the server may already have
acted. Inputs are validated before any I/O and rejected with a scrubbed
``CasaRequestError`` that never echoes the input.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import stat
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, JsonValue, ValidationError

from casahome._common import _parse, _write_home, _write_id, unverified
from casahome.client import CasaClient
from casahome.exceptions import CasaRequestError, CasaResponseError
from casahome.models.ai import CasaAIFeedbackResponse, CasaAISendMessageResponse
from casahome.models.documents import (
    CreateDocumentResponse,
    DocumentTypesResponse,
    DocumentUploadSessionsResponse,
    SavedResponse,
)
from casahome.models.entity_publish import (
    RenameRoomRequest,
    SaveAndPublishEntityRequest,
    SaveAndPublishEntityResponse,
)
from casahome.models.mailbox import MailboxClaimResponse
from casahome.models.preferences import AccessPreferencesResponse, NotificationSettingsResponse
from casahome.models.read_todos import TodoDetailsResponse
from casahome.models.verified_writes import (
    AnswerTodoQuestionRequest,
    CreateDocumentRequest,
    CreateDocumentUploadSessionRequest,
    DocumentUploadFile,
    MaterializeTodoRequest,
    MultiSelectAnswer,
    MultiSelectRoundAnswer,
    NotificationSettingUpdate,
    RateCasaAIMessageRequest,
    RespondToDocumentStructureSuggestionRequest,
    RespondToSuggestedTodoRequest,
    SendCasaAIMessageRequest,
    SingleSelectAnswer,
    SingleSelectRoundAnswer,
    SubmitQuestionRoundRequest,
    UpdateAccessPreferencesRequest,
    UpdateAutopilotPlanRequest,
    UpdateNotificationSettingsRequest,
)
from casahome.models.write_contracts import BasicMessageResponse, _write_payload
from casahome.uploads import put_storage_bytes

_IDEMPOTENCY_KEY = re.compile(r"[\x21-\x7e]{1,255}")


@dataclass(frozen=True)
class SentCasaAIMessage:
    """Result of ``send_ai_message``.

    ``idempotency_key`` is the ``Idempotency-Key`` header that was sent.
    Server deduplication hasn't been tested. After a timeout or connection
    error, check the thread before deciding whether to resend anything.
    """

    idempotency_key: str
    response: CasaAISendMessageResponse


def _body(schema: type[BaseModel], data: Mapping[str, Any], *, exclude_none: bool) -> Any:
    """Validate a request body and JSON-encode it, raising a scrubbed error."""
    try:
        validated = schema.model_validate(data)
    except ValidationError as err:
        message = f"Invalid {schema.__name__} write body: {err.error_count()} validation error(s)"
    else:
        return validated.model_dump(mode="json", exclude_none=exclude_none)
    # Raised outside the handler. Pydantic errors echo the rejected input.
    raise CasaRequestError(message)


def _sequence(value: Sequence[Any], name: str) -> list[Any]:
    """Reject a bare string, which would otherwise split into characters."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CasaRequestError(f"{name} must be a list, not a string")
    return list(value)


def _idempotency_key(value: str | None) -> str:
    if value is None:
        return str(uuid.uuid4())
    if not isinstance(value, str) or not _IDEMPOTENCY_KEY.fullmatch(value):
        raise CasaRequestError("idempotency_key must be 1-255 visible ASCII characters")
    return value


def _filename(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 1024
        or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)
    ):
        raise CasaRequestError("filename must be 1-1024 characters without control characters")
    return value


class VerifiedWritesMixin:
    """Live-verified write methods. Mixed into ``CasaApi``."""

    client: CasaClient

    # Inventory ---------------------------------------------------------------

    async def save_and_publish_entity(
        self, home_id: str, entity_id: str, body: SaveAndPublishEntityRequest
    ) -> SaveAndPublishEntityResponse:
        """VERIFIED for the observed publish subset, not every selection. Sent once.

        Observed POST to the member-home entity's ``save_and_publish`` route
        with ``model.name`` and ``props: []``. Shared compiled selection encoding
        supports optional ``make`` and ``model``, each ``{"id": str}`` or
        ``{"name": str}``. Model-ID traffic remains UNVERIFIED. Observed responses
        answered HTTP 200 with entity_id,
        status="published", make, model and identity.state="verified". Names
        are matched against Casa's catalog. An unmatched name fails with HTTP
        400 ``CasaApiError`` code ``CATALOG_MODEL_UNVERIFIED``. Static clear encoding
        is explicit null, but server clearing semantics remain UNVERIFIED.
        Clear selections, nonempty props and props-only bodies aren't supported.
        No entity refresh or second write is performed.
        """
        path = f"{_write_home(home_id, member=True)}/entity/{_write_id(entity_id)}/save_and_publish"
        payload = _write_payload(body, SaveAndPublishEntityRequest)
        return _parse(SaveAndPublishEntityResponse, await self.client.post(path, json=payload))

    async def update_entity_model(
        self, home_id: str, entity_id: str, model_name: str
    ) -> SaveAndPublishEntityResponse:
        """VERIFIED name-only model update via save_and_publish, with empty props.

        Same as ``update_entity_make_model(..., model_name=model_name)``. The
        supplied name is sent as given. Blank names are rejected, since
        empty-name/clear semantics are UNVERIFIED.
        """
        return await self.update_entity_make_model(home_id, entity_id, model_name=model_name)

    async def update_entity_make_model(
        self,
        home_id: str,
        entity_id: str,
        *,
        make_id: str | None = None,
        make_name: str | None = None,
        model_id: str | None = None,
        model_name: str | None = None,
    ) -> SaveAndPublishEntityResponse:
        """Set an item's make and/or model via save_and_publish, with scoped evidence.

        Pass at most one of ``make_id``/``make_name`` and at most one of
        ``model_id``/``model_name``, and at least one side overall. An omitted
        side isn't sent. The body always carries ``props: []``.

        Both the ``{"id": ...}`` and ``{"name": ...}`` variants are supported by
        the shared compiled selection codec. That static evidence doesn't prove
        every variant was observed in traffic. Model-ID traffic is UNVERIFIED.
        Populated responses were observed with ``identity.state="verified"``.
        Casa matches names against its catalog
        and may store a different canonical name, so read the returned
        ``make.name`` and ``model.name`` when present. A name it can't match raises
        ``CasaApiError`` with status 400 and code ``CATALOG_MODEL_UNVERIFIED``.
        Clearing isn't supported. Its compiled wire form is explicit null, but
        server clearing semantics remain UNVERIFIED. ``None`` omits a side.
        """
        body: dict[str, Any] = {"props": []}
        for side, id_value, name_value in (
            ("make", make_id, make_name),
            ("model", model_id, model_name),
        ):
            if id_value is not None and name_value is not None:
                raise CasaRequestError(f"pass at most one of {side}_id and {side}_name")
            if id_value is not None:
                body[side] = {"id": id_value}
            elif name_value is not None:
                body[side] = {"name": name_value}
        if "make" not in body and "model" not in body:
            raise CasaRequestError("pass a make or model id or name")
        path = f"{_write_home(home_id, member=True)}/entity/{_write_id(entity_id)}/save_and_publish"
        payload = _body(SaveAndPublishEntityRequest, body, exclude_none=True)
        return _parse(SaveAndPublishEntityResponse, await self.client.post(path, json=payload))

    async def rename_room(
        self, home_id: str, room_id: str, *, room_type_id: str, name: str
    ) -> BasicMessageResponse:
        """VERIFIED (live, 2026-10). Rename a room and set its room type.

        Observed ``PATCH /protected/member/home/{home_id}/room/{room_id}`` with
        ``{"room_type_id": str, "name": str}``, answered HTTP 200
        ``{"message": "Room updated"}``. Both keys are always sent. Pass the
        room's current ``room_type_id`` to keep its type. Partial bodies aren't
        verified, so neither key is optional.
        """
        path = f"{_write_home(home_id, member=True)}/room/{_write_id(room_id)}"
        payload = _body(
            RenameRoomRequest, {"room_type_id": room_type_id, "name": name}, exclude_none=False
        )
        return _parse(BasicMessageResponse, await self.client.patch(path, json=payload))

    async def move_entity_to_room(
        self, home_id: str, entity_id: str, room_id: str
    ) -> BasicMessageResponse:
        """VERIFIED (live, 2026-10). Move an inventory item to another room.

        Observed ``POST /protected/member/home/{home_id}/entity/{entity_id}/room/{room_id}``
        with no body, answered HTTP 200 ``{"message": str}``. The server replaces
        the entity's room: afterwards the entity is only in the new room.
        """
        entity, room = _write_id(entity_id), _write_id(room_id)
        path = f"{_write_home(home_id, member=True)}/entity/{entity}/room/{room}"
        return _parse(BasicMessageResponse, await self.client.post(path))

    # Casa AI -----------------------------------------------------------------

    async def send_ai_message(
        self,
        home_id: str,
        text: str,
        *,
        upload_ids: Sequence[str] = (),
        idempotency_key: str | None = None,
    ) -> SentCasaAIMessage:
        """VERIFIED (live, 2026-10). Send a message to Casa AI.

        Observed ``POST /protected/home/{home_id}/casa_ai/messages`` with an
        ``Idempotency-Key`` header and body ``{"input": {"type": "message",
        "text": str, "upload_ids": [str]}}``, answered HTTP 202 with
        ``member_message`` and ``active_response``. The assistant's reply
        arrives on ``casa_ai_events``, not in this response.

        ``text`` must be 1-10,000 characters. A fresh UUID4 key is generated
        when ``idempotency_key`` is None. The key used is returned for tracing
        and caller-controlled recovery, not as a guarantee that retries are safe.
        Server-side deduplication hasn't been tested. A failed send may have
        succeeded, so check the thread before considering another attempt.
        """
        path = f"{_write_home(home_id)}/casa_ai/messages"
        key = _idempotency_key(idempotency_key)
        payload = _body(
            SendCasaAIMessageRequest,
            {"input": {"text": text, "upload_ids": _sequence(upload_ids, "upload_ids")}},
            exclude_none=True,
        )
        data = await self.client.request(
            "POST", path, json=payload, headers={"Idempotency-Key": key}
        )
        return SentCasaAIMessage(key, _parse(CasaAISendMessageResponse, data))

    async def rate_ai_message(
        self, home_id: str, message_id: str, rating: Literal["good", "bad"]
    ) -> CasaAIFeedbackResponse:
        """VERIFIED (live, 2026-10). Thumbs up or down on an assistant message.

        Observed ``PUT /protected/home/{home_id}/casa_ai/messages/{message_id}/feedback``
        with ``{"rating": "good"|"bad"}``, answered HTTP 200 ``{"success": bool,
        "feedback": {"rating": str}}``.
        """
        path = f"{_write_home(home_id)}/casa_ai/messages/{_write_id(message_id)}/feedback"
        payload = _body(RateCasaAIMessageRequest, {"rating": rating}, exclude_none=True)
        return _parse(CasaAIFeedbackResponse, await self.client.put(path, json=payload))

    @unverified
    async def clear_ai_message_rating(self, home_id: str, message_id: str) -> JsonValue:
        """Remove a rating from an assistant message.

        ``DELETE`` on the same path as ``rate_ai_message``, from static app
        evidence only. The response shape is unknown, so the decoded JSON is
        returned as-is (None for an empty body).
        """
        path = f"{_write_home(home_id)}/casa_ai/messages/{_write_id(message_id)}/feedback"
        result: JsonValue = await self.client.delete(path)
        return result

    # To-dos ------------------------------------------------------------------

    async def delete_todo(self, home_id: str, todo_id: str) -> None:
        """VERIFIED. DELETE the home's todo with no body, answered HTTP 204.

        One attempt, including on 401. No automatic cleanup of related work.
        """
        path = f"{_write_home(home_id)}/todos/{_write_id(todo_id)}"
        await self.client.delete(path)

    async def answer_todo_question(
        self,
        home_id: str,
        todo_id: str,
        round_id: str,
        question_id: str,
        *,
        answer: SingleSelectAnswer | MultiSelectAnswer | None = None,
        skip: bool = False,
    ) -> None:
        """VERIFIED (live, 2026-10) for answers. Save one question's answer.

        Observed ``PUT /protected/home/{home_id}/todos/{todo_id}/question_rounds/
        {round_id}/questions/{question_id}/answer`` with ``{"is_skipped": false,
        "answer": {"kind": "single_select", "other_text": null,
        "selected_option_index": 0}}`` (or ``multi_select`` with
        ``selected_option_indexes``), answered HTTP 204 with no body.

        Pass exactly one of ``answer`` or ``skip=True``. Skipping sends
        ``{"is_skipped": true, "answer": null}``. That skip body is UNVERIFIED:
        only answered questions were observed.

        This saves the answer. ``submit_todo_question_round`` sends the round.
        """
        if not isinstance(skip, bool):
            raise CasaRequestError("skip must be a bool")
        if skip == (answer is not None):
            raise CasaRequestError("pass exactly one of answer or skip=True")
        path = (
            f"{_write_home(home_id)}/todos/{_write_id(todo_id)}"
            f"/question_rounds/{_write_id(round_id)}/questions/{_write_id(question_id)}/answer"
        )
        payload = _body(
            AnswerTodoQuestionRequest, {"is_skipped": skip, "answer": answer}, exclude_none=False
        )
        await self.client.put(path, json=payload)

    async def submit_todo_question_round(
        self,
        home_id: str,
        todo_id: str,
        round_id: str,
        answers: Sequence[SingleSelectRoundAnswer | MultiSelectRoundAnswer],
    ) -> TodoDetailsResponse:
        """VERIFIED (live, 2026-10). Submit a round of answers.

        Observed ``POST /protected/home/{home_id}/todos/{todo_id}/question_rounds/
        {round_id}/answers`` with ``{"answers": [{"question_id": str,
        "input_kind": "single_select", "selected_option_index": int,
        "other_text": null}]}`` (``multi_select`` uses
        ``selected_option_indexes``), answered HTTP 202 ``{"todo": ...}``.
        """
        path = (
            f"{_write_home(home_id)}/todos/{_write_id(todo_id)}"
            f"/question_rounds/{_write_id(round_id)}/answers"
        )
        payload = _body(
            SubmitQuestionRoundRequest,
            {"answers": _sequence(answers, "answers")},
            exclude_none=False,
        )
        return _parse(TodoDetailsResponse, await self.client.post(path, json=payload))

    async def respond_to_suggested_todo(
        self, home_id: str, suggestion_id: str, decision: str
    ) -> TodoDetailsResponse:
        """VERIFIED (live, 2026-10) for ``decision="accept"``.

        Observed ``POST /protected/home/{home_id}/suggested_todos/{suggestion_id}/respond``
        with ``{"decision": "accept"}``, answered HTTP 202 ``{"todo": ...}``.
        The value for declining wasn't observed, so ``decision`` is a plain
        string. Use ``"accept"``. Other values are sent as given.
        """
        path = f"{_write_home(home_id)}/suggested_todos/{_write_id(suggestion_id)}/respond"
        payload = _body(RespondToSuggestedTodoRequest, {"decision": decision}, exclude_none=True)
        return _parse(TodoDetailsResponse, await self.client.post(path, json=payload))

    async def materialize_todo(
        self, home_id: str, todo_id: str, destination: str = "concierge"
    ) -> TodoDetailsResponse:
        """VERIFIED (live, 2026-10) for ``destination="concierge"``.

        Observed ``POST /protected/home/{home_id}/todos/{todo_id}/materialize``
        with ``{"destination": "concierge"}``, answered HTTP 201 ``{"todo": ...}``
        whose ``destination`` became ``{"kind": "request", "id": ...}``. Other
        destination values weren't observed.
        """
        path = f"{_write_home(home_id)}/todos/{_write_id(todo_id)}/materialize"
        payload = _body(MaterializeTodoRequest, {"destination": destination}, exclude_none=True)
        return _parse(TodoDetailsResponse, await self.client.post(path, json=payload))

    async def send_todo_to_concierge(self, home_id: str, todo_id: str) -> TodoDetailsResponse:
        """VERIFIED (live, 2026-10). Hand a to-do to the concierge as a request.

        Same call as ``materialize_todo(home_id, todo_id, "concierge")``.
        """
        return await self.materialize_todo(home_id, todo_id, "concierge")

    # Settings ----------------------------------------------------------------

    async def update_autopilot_plan(
        self,
        home_id: str,
        plan_id: str,
        *,
        enabled: bool,
        selected_cadence: str,
        next_desired_occurrence_date: date,
        associations_enabled_map: Mapping[str, bool] | None = None,
    ) -> BasicMessageResponse:
        """VERIFIED (live, 2026-10). Update one Autopilot plan's settings.

        Observed ``PATCH /protected/home/{home_id}/autopilot/{plan_id}`` with
        ``{"next_desired_occurrence_date": "YYYY-MM-DD", "selected_cadence":
        "every_quarter", "associations_enabled_map": {}, "enabled": bool}``,
        answered HTTP 200 ``{"message": str}``. All four keys are always sent.
        ``None`` for the map sends ``{}``, as observed. Whether ``{}`` leaves
        existing associations unchanged is UNVERIFIED.
        """
        if isinstance(next_desired_occurrence_date, datetime):
            raise CasaRequestError("next_desired_occurrence_date must be a date, not a datetime")
        if associations_enabled_map is not None and not isinstance(
            associations_enabled_map, Mapping
        ):
            raise CasaRequestError("associations_enabled_map must be a mapping")
        path = f"{_write_home(home_id)}/autopilot/{_write_id(plan_id)}"
        payload = _body(
            UpdateAutopilotPlanRequest,
            {
                "next_desired_occurrence_date": next_desired_occurrence_date,
                "selected_cadence": selected_cadence,
                "associations_enabled_map": dict(associations_enabled_map or {}),
                "enabled": enabled,
            },
            exclude_none=True,
        )
        return _parse(BasicMessageResponse, await self.client.patch(path, json=payload))

    async def update_notification_settings(
        self, home_id: str, settings: Sequence[NotificationSettingUpdate]
    ) -> NotificationSettingsResponse:
        """VERIFIED (live, 2026-10). Toggle notification type/channel pairs.

        Observed ``PUT /protected/home/{home_id}/notification_settings`` with
        ``{"settings": [{"notification_type": str, "channel": "push",
        "enabled": bool}]}``, answered HTTP 200 with the full grouped settings
        (same shape as ``notification_settings``). Only listed pairs were sent.
        """
        path = f"{_write_home(home_id)}/notification_settings"
        payload = _body(
            UpdateNotificationSettingsRequest,
            {"settings": _sequence(settings, "settings")},
            exclude_none=True,
        )
        return _parse(NotificationSettingsResponse, await self.client.put(path, json=payload))

    async def update_access_preferences(
        self,
        home_id: str,
        *,
        general_instructions: str | None,
        package_pickup_method: str | None,
        package_pickup_spot: str | None,
        package_pickup_general_instructions: str | None,
    ) -> AccessPreferencesResponse:
        """VERIFIED (live, 2026-10). Set home access and package pickup notes.

        Observed ``PATCH /protected/home/{home_id}/access_preferences`` with all
        four keys (``package_pickup_method`` seen as ``pickup_spot``,
        ``package_pickup_spot`` as ``other``), answered HTTP 200 with the same
        shape as ``access_preferences``. Every key is required here and
        ``None`` is sent as ``null``. Whether ``null`` clears a value or
        leaves it unchanged is UNVERIFIED.
        """
        path = f"{_write_home(home_id)}/access_preferences"
        payload = _body(
            UpdateAccessPreferencesRequest,
            {
                "general_instructions": general_instructions,
                "package_pickup_method": package_pickup_method,
                "package_pickup_spot": package_pickup_spot,
                "package_pickup_general_instructions": package_pickup_general_instructions,
            },
            exclude_none=False,
        )
        return _parse(AccessPreferencesResponse, await self.client.patch(path, json=payload))

    async def claim_mailbox(self, home_id: str) -> MailboxClaimResponse:
        """VERIFIED (live, 2026-10). Claim the home's Casa mailbox.

        Observed ``POST /protected/home/{home_id}/mailbox/claim`` with no body,
        answered HTTP 200 ``{"mailbox": {...}}`` with id, status, onboarding
        status, address and the other ``MemberMailbox`` fields.
        """
        path = f"{_write_home(home_id)}/mailbox/claim"
        return _parse(MailboxClaimResponse, await self.client.post(path))

    # Documents ---------------------------------------------------------------

    async def respond_to_document_structure_suggestion(
        self,
        home_id: str,
        document_id: str,
        suggestion_id: str,
        expected_values: Sequence[str],
        decision: Literal["accepted"] = "accepted",
    ) -> SavedResponse:
        """VERIFIED for decision=accepted and the required expected_values guard.

        Observed POST to ``documents/{document_id}/structure_suggestions/
        {suggestion_id}/respond`` with ``{"decision": "accepted",
        "expected_values": [str]}``, answered HTTP 200 ``{"saved": true}``.
        The base is /protected/home, not /protected/member/home.

        Pass the suggestion's current_values explicitly. The SDK preserves
        their order and content. It never invents a default, re-fetches values
        or retries a stale guard. Server mismatch handling remains UNVERIFIED.
        Only accepted is supported. Accept and dismissal variants are rejected.
        One attempt, including on 401. No document PATCH or automatic follow-up.
        """
        path = (
            f"{_write_home(home_id)}/documents/{_write_id(document_id)}"
            f"/structure_suggestions/{_write_id(suggestion_id)}/respond"
        )
        payload = _body(
            RespondToDocumentStructureSuggestionRequest,
            {
                "decision": decision,
                "expected_values": _sequence(expected_values, "expected_values"),
            },
            exclude_none=True,
        )
        return _parse(SavedResponse, await self.client.post(path, json=payload))

    async def create_document_upload_sessions(
        self, home_id: str, files: Sequence[DocumentUploadFile]
    ) -> DocumentUploadSessionsResponse:
        """VERIFIED (live, 2026-10). Upload step 1: reserve upload slots.

        Observed ``POST /protected/home/{home_id}/documents/sessions`` with
        ``{"files": [{"size_bytes": int, "mimetype": str}]}``, answered HTTP 200
        ``{"uploads": [{"upload_id": str, "session_url": str}]}``. Each
        ``session_url`` is a signed Cloud Storage URL. Treat it as a secret.
        """
        path = f"{_write_home(home_id)}/documents/sessions"
        payload = _body(
            CreateDocumentUploadSessionRequest,
            {"files": _sequence(files, "files")},
            exclude_none=True,
        )
        data = await self.client.post(path, json=payload)
        return _parse(DocumentUploadSessionsResponse, data)

    async def upload_document_content(self, session_url: str, data: bytes, mimetype: str) -> None:
        """VERIFIED (live, 2026-10). Upload step 2: send the file bytes.

        Observed ``PUT`` to the ``session_url`` from step 1 (an
        ``https://storage.googleapis.com/...`` resumable upload URL) with the
        raw bytes and ``Content-Type``, ``Content-Length`` and ``Content-Range:
        bytes 0-{n-1}/{n}``, answered HTTP 200.

        Only https URLs on storage.googleapis.com are accepted. No Casa
        credentials or app headers are sent. Storage owns a separate session
        with no caller auth, cookies, headers or middleware. TLS verification
        stays enabled. One attempt, no redirects. The whole file goes in one
        request, so it's held in memory. The caller's Casa session stays open.
        """
        if not isinstance(mimetype, str) or not mimetype or len(mimetype) > 128:
            raise CasaRequestError("mimetype must be a nonempty string")
        await put_storage_bytes(
            self.client._session, session_url, data, mimetype, timeout=self.client._timeout
        )

    async def create_document(
        self,
        home_id: str,
        upload_id: str,
        original_filename: str,
        *,
        find_todos: bool = True,
    ) -> CreateDocumentResponse:
        """VERIFIED (live, 2026-10). Upload step 3: register the uploaded file.

        Observed ``POST /protected/home/{home_id}/documents`` with
        ``{"find_todos": bool, "upload_id": str, "original_filename": str}``,
        answered HTTP 201 ``{"document": {...}, "already_exists": bool}``.
        ``find_todos`` asks Casa to suggest to-dos from the document.
        """
        path = f"{_write_home(home_id)}/documents"
        payload = _body(
            CreateDocumentRequest,
            {
                "find_todos": find_todos,
                "upload_id": upload_id,
                "original_filename": _filename(original_filename),
            },
            exclude_none=True,
        )
        return _parse(CreateDocumentResponse, await self.client.post(path, json=payload))

    async def upload_document(
        self,
        home_id: str,
        source: bytes | str | os.PathLike[str],
        filename: str,
        mimetype: str | None = None,
        *,
        find_todos: bool = True,
    ) -> CreateDocumentResponse:
        """VERIFIED (live, 2026-10) flow. Upload one file as a home document.

        Runs the three observed steps: ``create_document_upload_sessions``,
        ``upload_document_content`` and ``create_document``. Before any write
        it reads ``documents/types`` and checks the MIME type against
        ``allowed_mimetypes`` and the size against ``max_file_size_bytes``.

        ``source`` is the file content or a local path. ``mimetype`` is guessed
        from ``filename`` when omitted. Each step is sent once. If a later step
        fails, the earlier ones aren't undone. An unregistered upload is
        simply never attached to a document.

        Local paths must open as nonempty regular files. Symlinks to regular
        files are allowed. Reads are bounded to max_file_size_bytes plus one
        detection byte, even if the file grows. The configured client total
        timeout bounds waiting for the read, but cancellation can't interrupt
        a filesystem call already running in the worker thread.
        """
        home_id = _write_id(home_id)
        filename = _filename(filename)
        if not isinstance(source, (bytes, str, os.PathLike)):
            raise CasaRequestError("source must be bytes or a file path")
        if not isinstance(find_todos, bool):
            raise CasaRequestError("find_todos must be a bool")
        resolved = mimetype if mimetype is not None else mimetypes.guess_type(filename)[0]
        if not resolved:
            raise CasaRequestError("mimetype could not be guessed from filename")

        policy = _parse(
            DocumentTypesResponse,
            await self.client.get(f"{_write_home(home_id)}/documents/types"),
        )
        if resolved not in policy.allowed_mimetypes:
            raise CasaRequestError("mimetype is not an allowed document type")

        if isinstance(source, bytes):
            content = source
        else:
            content = await _read_bounded(
                Path(source), policy.max_file_size_bytes, timeout=self.client._timeout.total
            )
        if not 0 < len(content) <= policy.max_file_size_bytes:
            raise CasaRequestError("file must be nonempty and within max_file_size_bytes")

        sessions = await self.create_document_upload_sessions(
            home_id, [DocumentUploadFile(size_bytes=len(content), mimetype=resolved)]
        )
        if len(sessions.uploads) != 1:
            raise CasaResponseError("Expected exactly one upload session")
        upload = sessions.uploads[0]
        await self.upload_document_content(upload.session_url, content, resolved)
        return await self.create_document(
            home_id, upload.upload_id, filename, find_todos=find_todos
        )


async def _read_bounded(path: Path, limit: int, *, timeout: float | None = None) -> bytes:
    """Open once, reject special files, and read at most limit plus one byte.

    O_NONBLOCK keeps FIFO opens from waiting for a writer. fstat checks the
    opened descriptor, not a racy pathname. Symlinks to regular files are
    allowed. A timeout bounds the await, not an in-flight filesystem syscall.
    The worker always closes its descriptor when it finishes.
    """

    def read() -> bytes | None:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return b""
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                return b""
            if info.st_size > limit:
                return None
            content = bytearray()
            while len(content) <= limit:
                chunk = os.read(descriptor, min(64 * 1024, limit + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            return bytes(content) if len(content) <= limit else None
        except OSError:
            return b""
        finally:
            os.close(descriptor)

    try:
        async with asyncio.timeout(timeout):
            content = await asyncio.to_thread(read)
    except TimeoutError:
        message = "file read timed out"
    else:
        if content is None:
            raise CasaRequestError("file exceeds max_file_size_bytes")
        if not content:
            raise CasaRequestError("file could not be read, isn't regular, or is empty")
        return content
    raise CasaRequestError(message)
