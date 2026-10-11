"""Typed read envelopes without changing the existing create_todo return model."""

from pydantic import Field

from casahome.models._base import CasaModel
from casahome.models.images import MediaAttachment
from casahome.models.todos import TodoDetail


class TodoReadDetail(TodoDetail):
    """Populated core fields and attachments observed. Other nested fields static."""

    flagged_for_support: bool = False
    attachments: list[MediaAttachment] = Field(default_factory=list)


class TodoDetailsResponse(CasaModel):
    todo: TodoReadDetail


class SuggestedTodosResponse(CasaModel):
    suggested_todos: list[TodoReadDetail]
