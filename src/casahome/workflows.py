"""Isolated provisional workflow writes. No live server verification.

Compiled client routes, methods, request codecs and response bindings were
recovered statically. Cancellation's nested decoder remains partial. Every
method is marked unverified and makes one explicit write, with no automatic
refresh of workflow state, follow-up mutation or retry after an unknown outcome.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from casahome._common import _parse, _write_home, _write_id, unverified
from casahome.client import CasaClient
from casahome.exceptions import CasaRequestError
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.documents import DocumentDetailsResponse
from casahome.models.preferences import SchedulePreferencesResponse
from casahome.models.read_todos import TodoDetailsResponse
from casahome.models.workflows import (
    AnalyzeDocumentRequest,
    CancelVendorVisitResponse,
    ConfirmTodoSupportRequest,
    MemberAvailabilitySlotWindow,
    RejectSuggestedTodoRequest,
    ReorderTodoSectionRequest,
    ReorderTodoSectionResponse,
    TodoOrderSection,
    TodoRejectionReason,
    UpdateAvailabilitySlotsRequest,
    UpdateDocumentBody,
    UpdateSchedulePreferencesRequest,
    UpdateTodoBody,
)
from casahome.models.write_contracts import _write_payload
from casahome.writes import _body, _sequence


def _document_payload(body: UpdateDocumentBody) -> dict[str, Any]:
    """Revalidate without losing unset versus explicitly null document dates."""
    if not isinstance(body, UpdateDocumentBody):
        raise CasaRequestError("write body must be an UpdateDocumentBody")
    try:
        validated = UpdateDocumentBody.model_validate(body)
    except ValidationError as err:
        message = f"Invalid UpdateDocumentBody write body: {err.error_count()} validation error(s)"
    else:
        payload = validated.model_dump(mode="json", exclude_unset=True)
        return {
            key: value
            for key, value in payload.items()
            if key == "document_date" or value is not None
        }
    # Pydantic errors can contain private input. Drop even implicit context.
    raise CasaRequestError(message)


class ProvisionalWorkflowMixin:
    """Opt-in workflow surface for CasaApi wiring. All methods are UNVERIFIED.

    CasaClient force-refreshes auth before writes and doesn't retry a 401.
    Caller-supplied IDs and bodies are validated before that auth I/O begins.
    Server-side effects, permissions and safe retry behavior remain unknown.
    """

    client: CasaClient

    @unverified
    async def update_todo(
        self, home_id: str, todo_id: str, body: UpdateTodoBody
    ) -> TodoDetailsResponse:
        """PATCH optional todo edits and attachment deltas once.

        None omits a field recursively. Empty strings and [] are preserved.
        Clearing semantics and upload lifecycle are UNVERIFIED. No upload is
        created and no support classification is chosen automatically.
        """
        path = f"{_write_home(home_id)}/todos/{_write_id(todo_id)}"
        if not isinstance(body, UpdateTodoBody):
            raise CasaRequestError("write body must be an UpdateTodoBody")
        payload = _write_payload(body, UpdateTodoBody)
        return _parse(TodoDetailsResponse, await self.client.patch(path, json=payload))

    @unverified
    async def reject_suggested_todo(
        self, home_id: str, todo_id: str, reason: TodoRejectionReason | None = None
    ) -> TodoDetailsResponse:
        """Reject a suggestion with optional dismissed or already_handled reason.

        Sends decision=reject, never a Swift case spelling. None omits reason.
        Reason requirements and server rejection policy remain UNVERIFIED.
        The existing respond_to_suggested_todo method isn't changed.
        """
        path = f"{_write_home(home_id)}/suggested_todos/{_write_id(todo_id)}/respond"
        payload = _body(RejectSuggestedTodoRequest, {"reason": reason}, exclude_none=True)
        return _parse(TodoDetailsResponse, await self.client.post(path, json=payload))

    @unverified
    async def confirm_todo_support(
        self, home_id: str, todo_id: str, is_support_question: bool
    ) -> TodoDetailsResponse:
        """Send the caller's required, strict Boolean support decision once.

        Both true and false are encoded. No default or inferred classification.
        Server-side consequences remain UNVERIFIED.
        """
        path = f"{_write_home(home_id)}/todos/{_write_id(todo_id)}/support_confirmation"
        payload = _body(
            ConfirmTodoSupportRequest,
            {"is_support_question": is_support_question},
            exclude_none=True,
        )
        return _parse(TodoDetailsResponse, await self.client.post(path, json=payload))

    @unverified
    async def update_document(
        self, home_id: str, document_id: str, body: UpdateDocumentBody
    ) -> DocumentDetailsResponse:
        """PATCH name/type and omitted, string or explicitly null document_date.

        An unset date never silently clears it. None omits name and type.
        Date format, document-type vocabulary and null clearing semantics remain
        UNVERIFIED. Requires the actual document response wrapper, not raw JSON.
        """
        path = f"{_write_home(home_id)}/documents/{_write_id(document_id)}"
        payload = _document_payload(body)
        return _parse(DocumentDetailsResponse, await self.client.patch(path, json=payload))

    @unverified
    async def analyze_document(
        self, home_id: str, document_id: str, reanalyze: bool
    ) -> DocumentDetailsResponse:
        """Start analysis with an explicitly supplied strict Boolean.

        The true/false distinction and existing-work invalidation are
        UNVERIFIED. No automatic reanalysis, polling or mutation retry.
        """
        path = f"{_write_home(home_id)}/documents/{_write_id(document_id)}/analysis"
        payload = _body(AnalyzeDocumentRequest, {"reanalyze": reanalyze}, exclude_none=True)
        return _parse(DocumentDetailsResponse, await self.client.post(path, json=payload))

    @unverified
    async def organize_document(self, home_id: str, document_id: str) -> DocumentDetailsResponse:
        """Start document organization with a bodyless POST, not {}.

        Background-work effects and concurrent organization are UNVERIFIED.
        No inferred analysis flags, automatic polling or retry.
        """
        path = f"{_write_home(home_id)}/documents/{_write_id(document_id)}/organization"
        return _parse(DocumentDetailsResponse, await self.client.post(path))

    @unverified
    async def update_schedule_preferences(
        self, home_id: str, body: UpdateSchedulePreferencesRequest
    ) -> SchedulePreferencesResponse:
        """PUT both required day and time-window selections, even when empty.

        Weekday numbering, allowed IDs, empty selection acceptance and
        replacement versus merge behavior remain UNVERIFIED.
        """
        path = f"{_write_home(home_id)}/schedule_preferences"
        if not isinstance(body, UpdateSchedulePreferencesRequest):
            raise CasaRequestError("write body must be an UpdateSchedulePreferencesRequest")
        payload = _write_payload(body, UpdateSchedulePreferencesRequest)
        return _parse(SchedulePreferencesResponse, await self.client.put(path, json=payload))

    @unverified
    async def update_availability_slots(
        self,
        home_id: str,
        availability_request_id: str,
        windows: Sequence[MemberAvailabilitySlotWindow],
    ) -> MemberAvailabilityDetail:
        """PUT required integer slot windows once. Time units are UNVERIFIED.

        No datetime conversion or ordering, duration or overlap rules are
        invented. [] remains []. Replacement semantics and whether this also
        finalizes submission are UNVERIFIED. No separate submit is implied.
        """
        path = (
            f"{_write_home(home_id)}/availability_requests/"
            f"{_write_id(availability_request_id)}/slots"
        )
        payload = _body(
            UpdateAvailabilitySlotsRequest,
            {"slots": _sequence(windows, "windows")},
            exclude_none=True,
        )
        return _parse(MemberAvailabilityDetail, await self.client.put(path, json=payload))

    @unverified
    async def reorder_todo_section(
        self,
        home_id: str,
        section: TodoOrderSection,
        *,
        expected_revision: int,
        ordered_item_ids: Sequence[str],
    ) -> ReorderTodoSectionResponse:
        """PUT an explicit revision guard and caller-ordered item IDs once.

        Only ready_for_scheduling and send_to_concierge routes are recovered.
        Stale-revision handling and full-section enumeration requirements remain
        UNVERIFIED. Never automatically refetch or resubmit a stale list.
        """
        home = _write_home(home_id)
        section_id = _write_id(section)
        if section_id not in {"ready_for_scheduling", "send_to_concierge"}:
            raise CasaRequestError("section must be ready_for_scheduling or send_to_concierge")
        path = f"{home}/requests_tab/todo_sections/{section_id}/order"
        payload = _body(
            ReorderTodoSectionRequest,
            {
                "expected_revision": expected_revision,
                "ordered_item_ids": _sequence(ordered_item_ids, "ordered_item_ids"),
            },
            exclude_none=True,
        )
        return _parse(ReorderTodoSectionResponse, await self.client.put(path, json=payload))

    @unverified
    async def retry_todo(self, home_id: str, todo_id: str) -> TodoDetailsResponse:
        """Explicit preparation retry via one bodyless POST, not {}.

        Idempotency and new preparation/question-round creation remain
        UNVERIFIED. This explicit action never retries itself automatically.
        """
        path = f"{_write_home(home_id)}/todos/{_write_id(todo_id)}/retry"
        return _parse(TodoDetailsResponse, await self.client.post(path))

    @unverified
    async def cancel_vendor_visit(self, home_id: str, visit_id: str) -> CancelVendorVisitResponse:
        """Cancel one visit with bodyless PUT /cancelation, spelled with one l.

        Cancellation fees and maintenance side effects are possible and
        UNVERIFIED. The selected response type is recovered, but nested decoder
        recovery is PARTIAL_STATIC. Status is an open enum field, not a success
        flag. No inferred reason, request-reservation cancellation or retry.
        """
        path = f"{_write_home(home_id)}/vendor_visits/{_write_id(visit_id)}/cancelation"
        return _parse(CancelVendorVisitResponse, await self.client.put(path))
