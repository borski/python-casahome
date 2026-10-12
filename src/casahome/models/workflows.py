"""Provisional workflow codecs recovered from compiled client code.

All server contracts remain UNVERIFIED. The write models reject coercion and
unknown fields. Text is capped at 10,000 characters and lists at 100 entries
as SDK safety policy, not as claims about server limits.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StrictBool, StrictInt, StrictStr

from casahome._common import _safe_id
from casahome.models._base import CasaModel
from casahome.models.enums import VendorVisitStatusField
from casahome.models.requests import TodosLaneSection
from casahome.models.write_contracts import WRITE_TEXT_MAX_CHARS, _WriteModel

_Text = Annotated[StrictStr, Field(max_length=WRITE_TEXT_MAX_CHARS)]
_Id = Annotated[StrictStr, Field(max_length=2048), AfterValidator(_safe_id)]
_Ids = Annotated[list[_Id], Field(max_length=100)]

TodoRejectionReason = Literal["dismissed", "already_handled"]
TodoOrderSection = Literal["ready_for_scheduling", "send_to_concierge"]


class UpdateTodoAttachmentsBody(_WriteModel):
    """Optional attachment deltas. None omits a key, [] is sent unchanged."""

    add_upload_ids: _Ids | None = None
    remove_attachment_ids: _Ids | None = None


class UpdateTodoBody(_WriteModel):
    """Optional edits omit None. Empty strings and deltas aren't inferred clears."""

    title: _Text | None = None
    prepared_brief: _Text | None = None
    emoji: _Text | None = None
    attachments: UpdateTodoAttachmentsBody | None = None


class RejectSuggestedTodoRequest(_WriteModel):
    """Distinct rejection codec, without changing the existing acceptance method."""

    decision: Literal["reject"] = "reject"
    reason: TodoRejectionReason | None = None


class ConfirmTodoSupportRequest(_WriteModel):
    is_support_question: StrictBool


class UpdateDocumentBody(_WriteModel):
    """Tri-state document date via Pydantic's model_fields_set.

    Leave document_date unset to omit it. Supply a string to set it or explicit
    None to emit JSON null. The API serializes with exclude_unset=True and
    retains that explicit null only for document_date. Name and type omit None.
    Date format, type vocabulary and server clearing behavior are UNVERIFIED.
    """

    name: _Text | None = None
    document_type: _Text | None = None
    document_date: _Text | None = None


class AnalyzeDocumentRequest(_WriteModel):
    reanalyze: StrictBool


class UpdateSchedulePreferencesRequest(_WriteModel):
    """Both selections are required, including empty lists.

    Weekday numbering and allowed window IDs remain UNVERIFIED. Use values
    returned by schedule_preferences, not a guessed numbering scheme.
    """

    selected_days_of_week: Annotated[list[StrictInt], Field(max_length=100)]
    selected_times_of_day: _Ids


class MemberAvailabilitySlotWindow(_WriteModel):
    """Required integer bounds. Units and ordering rules remain UNVERIFIED.

    No datetime conversion, positivity, duration or overlap policy is inferred.
    """

    start_time: StrictInt
    end_time: StrictInt


class UpdateAvailabilitySlotsRequest(_WriteModel):
    slots: Annotated[list[MemberAvailabilitySlotWindow], Field(max_length=100)]


class ReorderTodoSectionRequest(_WriteModel):
    """Explicit revision guard. No defaults, sorting, deduplication or retry."""

    expected_revision: StrictInt
    ordered_item_ids: _Ids


class ReorderTodoSectionResponse(CasaModel):
    """Required section envelope, reusing the existing typed todo lane section.

    Response binding is recovered statically. Nested server behavior and
    revision conflict handling remain UNVERIFIED.
    """

    section: TodosLaneSection


class CancelVendorVisitResponse(CasaModel):
    """Provisional id/status layout. Decoder recovery is PARTIAL_STATIC.

    The response type binding and field metadata are recovered, but required
    field decoding and the status wire mapping aren't fully traced. This SDK
    requires both fields and reuses the open enum field so new strings survive.
    A parsed response isn't proof of fee-free cancellation or final status.
    """

    id: StrictStr
    status: VendorVisitStatusField
