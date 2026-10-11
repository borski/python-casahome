"""Request bodies for writes VERIFIED against live app traffic (2026-10).

Every model is strict: unknown fields, coercion and oversized text are rejected
before any I/O. Field names and nullability match the observed request bodies.
Where the app sent an explicit ``null``, the encoder sends ``null`` too.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from casahome.models.write_contracts import WRITE_TEXT_MAX_CHARS, _WriteModel

_Text = Annotated[StrictStr, Field(max_length=WRITE_TEXT_MAX_CHARS)]
_Token = Annotated[StrictStr, Field(min_length=1, max_length=128)]
_Id = Annotated[StrictStr, Field(min_length=1, max_length=2048)]
_OptionIndex = Annotated[StrictInt, Field(ge=0)]


# Casa AI -----------------------------------------------------------------


class CasaAIMessageInput(_WriteModel):
    """``type`` is always ``message``. ``upload_ids`` is always sent, even empty."""

    type: Literal["message"] = "message"
    text: Annotated[StrictStr, Field(min_length=1, max_length=WRITE_TEXT_MAX_CHARS)]
    upload_ids: list[_Id] = Field(default_factory=list)


class SendCasaAIMessageRequest(_WriteModel):
    input: CasaAIMessageInput


class RateCasaAIMessageRequest(_WriteModel):
    rating: Literal["good", "bad"]


# To-do questions ---------------------------------------------------------


class SingleSelectAnswer(_WriteModel):
    """One chosen option. ``other_text`` is always sent, null when unused."""

    kind: Literal["single_select"] = "single_select"
    selected_option_index: _OptionIndex
    other_text: _Text | None = None


class MultiSelectAnswer(_WriteModel):
    """Several chosen options. ``other_text`` is always sent, null when unused."""

    kind: Literal["multi_select"] = "multi_select"
    selected_option_indexes: list[_OptionIndex]
    other_text: _Text | None = None


TodoQuestionAnswer = Annotated[SingleSelectAnswer | MultiSelectAnswer, Field(discriminator="kind")]


class AnswerTodoQuestionRequest(_WriteModel):
    is_skipped: StrictBool
    answer: TodoQuestionAnswer | None


class SingleSelectRoundAnswer(_WriteModel):
    question_id: _Id
    input_kind: Literal["single_select"] = "single_select"
    selected_option_index: _OptionIndex
    other_text: _Text | None = None


class MultiSelectRoundAnswer(_WriteModel):
    question_id: _Id
    input_kind: Literal["multi_select"] = "multi_select"
    selected_option_indexes: list[_OptionIndex]
    other_text: _Text | None = None


TodoRoundAnswer = Annotated[
    SingleSelectRoundAnswer | MultiSelectRoundAnswer, Field(discriminator="input_kind")
]


class SubmitQuestionRoundRequest(_WriteModel):
    answers: Annotated[list[TodoRoundAnswer], Field(min_length=1)]


class RespondToSuggestedTodoRequest(_WriteModel):
    decision: _Token


class MaterializeTodoRequest(_WriteModel):
    destination: _Token


# Settings ----------------------------------------------------------------


class UpdateAutopilotPlanRequest(_WriteModel):
    """Full plan settings. ``selected_cadence`` seen as ``every_quarter``."""

    next_desired_occurrence_date: date
    selected_cadence: _Token
    associations_enabled_map: dict[_Id, StrictBool]
    enabled: StrictBool


class NotificationSettingUpdate(_WriteModel):
    """One type/channel toggle. ``channel`` seen as ``push``."""

    notification_type: _Token
    channel: _Token
    enabled: StrictBool


class UpdateNotificationSettingsRequest(_WriteModel):
    settings: Annotated[list[NotificationSettingUpdate], Field(min_length=1)]


class UpdateAccessPreferencesRequest(_WriteModel):
    """All four keys are always sent. ``None`` is sent as ``null``.

    ``package_pickup_method`` seen as ``pickup_spot``, ``package_pickup_spot``
    seen as ``other``.
    """

    general_instructions: _Text | None
    package_pickup_method: _Token | None
    package_pickup_spot: _Token | None
    package_pickup_general_instructions: _Text | None


# Documents ---------------------------------------------------------------


class RespondToDocumentStructureSuggestionRequest(_WriteModel):
    """Only accepted was observed. The current-value race guard is required.

    No accept or dismissal decision variants are inferred. Explicit empty
    expected_values remains an empty list, not an omitted guard.
    """

    decision: Literal["accepted"]
    expected_values: list[_Text]


class DocumentUploadFile(_WriteModel):
    size_bytes: Annotated[StrictInt, Field(gt=0)]
    mimetype: _Token


class CreateDocumentUploadSessionRequest(_WriteModel):
    files: Annotated[list[DocumentUploadFile], Field(min_length=1)]


class CreateDocumentRequest(_WriteModel):
    find_todos: StrictBool
    upload_id: _Id
    original_filename: Annotated[StrictStr, Field(min_length=1, max_length=1024)]
