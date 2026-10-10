"""To-do models (UNVERIFIED endpoints)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ._base import CasaModel
from .enums import (
    TodoCreatorRoleField,
    TodoLaneCardKindField,
    TodoLaneCardStateField,
    TodoStatusField,
)


class AttachMediaPayload(CasaModel):
    upload_ids: list[str] = Field(default_factory=list)


class CreateTodoBody(CasaModel):
    content: str
    attachments: AttachMediaPayload | None = None


class TodoLaneCard(CasaModel):
    kind: TodoLaneCardKindField
    id: str
    title: str
    emoji: str
    updated_at: int
    state: TodoLaneCardStateField
    origin_todo_id: str | None = None
    can_delete: bool = False


class TodoDetail(CasaModel):
    id: str
    title: str
    emoji: str
    original_text: str
    prepared_brief: str
    status: TodoStatusField
    creator_role: TodoCreatorRoleField
    created_at: int
    updated_at: int
    can_delete: bool = False
    is_suggested: bool = False
    attachments: list[Any] = Field(default_factory=list)
    question_rounds: list[Any] = Field(default_factory=list)
    destination: Any | None = None
