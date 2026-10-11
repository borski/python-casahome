"""Typed read envelopes without changing the existing create_todo return model."""

from pydantic import Field, JsonValue

from casahome.models._base import CasaModel
from casahome.models.images import MediaAttachment
from casahome.models.todos import TodoDetail


class TodoQuestionRound(CasaModel):
    """A round of clarifying questions. VERIFIED (live, 2026-10).

    ``state`` seen as ``answered``. Question items stay JSON because their
    full shape isn't pinned.
    """

    id: str
    sequence: int | None = None
    state: str | None = None
    questions: list[JsonValue] = Field(default_factory=list)


class TodoDestination(CasaModel):
    """Where a to-do went. ``kind`` seen as ``request`` after concierge hand-off."""

    kind: str
    id: str | None = None


class TodoReadDetail(TodoDetail):
    """Full to-do detail. VERIFIED (live, 2026-10).

    Populated core fields, attachments, question rounds and destination
    observed. ``status`` seen as ``preparing`` and ``materialized``.
    """

    flagged_for_support: bool = False
    attachments: list[MediaAttachment] = Field(default_factory=list)
    question_rounds: list[TodoQuestionRound] = Field(default_factory=list)
    destination: TodoDestination | None = None


class TodoDetailsResponse(CasaModel):
    todo: TodoReadDetail


class SuggestedTodosResponse(CasaModel):
    suggested_todos: list[TodoReadDetail]
