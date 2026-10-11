"""Requests tab, request threads, and vendor visit models.

Request cards and request details are VERIFIED (live, 2026-10). Vendor visit
models remain static.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._base import CasaModel, epoch_to_dt
from .enums import (
    RequestStatusField,
    RequestTypeField,
    SenderRoleField,
    VendorVisitStatusField,
    VisitTypeField,
)
from .todos import TodoLaneCard


class Pagination(CasaModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int


class RequestCard(CasaModel):
    id: str
    type: RequestTypeField
    title: str
    emoji: str
    updated_at: int
    latest_message_preview: str | None = None
    has_unread_messages: bool = False
    pending_invoice_count: int = 0
    pending_purchase_count: int = 0
    pending_schedule_prompt_count: int = 0
    ready_to_review_availability_count: int = 0
    concierge_awaiting_reply: bool = False
    vendor_visits: list[Any] = Field(default_factory=list)

    @property
    def updated_at_dt(self) -> datetime | None:
        return epoch_to_dt(self.updated_at)


class RequestsSectionPresentation(CasaModel):
    title: str
    symbol: str | None = None


class RequestsLaneSection(CasaModel):
    name: str
    title: str
    symbol: str | None = None
    count: int | None = None
    items: list[RequestCard] = Field(default_factory=list)


class RequestsLane(CasaModel):
    needs_review: list[RequestCard] = Field(default_factory=list)
    completed: RequestsSectionPresentation | None = None
    completed_count: int = 0
    sections: list[RequestsLaneSection] = Field(default_factory=list)


class TasksLaneSection(CasaModel):
    name: str
    title: str
    symbol: str | None = None
    count: int | None = None
    items: list[Any] = Field(default_factory=list)  # TaskCard, not yet modeled


class TasksLane(CasaModel):
    sections: list[TasksLaneSection] = Field(default_factory=list)


class TodosLaneSection(CasaModel):
    name: str
    title: str
    items: list[TodoLaneCard] = Field(default_factory=list)
    order_revision: int | None = None


class TodosLane(CasaModel):
    sections: list[TodosLaneSection] = Field(default_factory=list)


class RequestsResponse(CasaModel):
    requests: RequestsLane
    tasks: TasksLane
    todos: TodosLane | None = None


class RequestMessage(CasaModel):
    id: str
    created_at: int
    sender_role: SenderRoleField
    sender_name: str
    sender_avatar_url: str | None = None
    sender_avatar_cache_key: str | None = None
    content: str | None = None
    attachments: list[Any] = Field(default_factory=list)
    scheduling_prompt: Any | None = None
    availability_request: Any | None = None
    invoice: Any | None = None
    purchase_approval_requests: list[Any] | None = None

    @property
    def created_at_dt(self) -> datetime | None:
        return epoch_to_dt(self.created_at)


class RequestSummary(CasaModel):
    """Request totals. ``total_spent`` is an integer amount, ``*_display`` is formatted."""

    scheduled_visit_count: int | None = None
    total_spent: int | None = None
    total_spent_display: str | None = None


class RequestDetails(CasaModel):
    id: str
    type: RequestTypeField
    status: RequestStatusField
    title: str
    emoji: str
    created_at: int
    updated_at: int
    has_unread_messages: bool = False
    summary: RequestSummary = Field(default_factory=RequestSummary)
    messages: list[RequestMessage] = Field(default_factory=list)
    visits: list[Any] = Field(default_factory=list)
    invoices: list[Any] = Field(default_factory=list)
    purchases: list[Any] = Field(default_factory=list)
    feedback: Any | None = None


class VendorVisitCalendarEvent(CasaModel):
    id: str
    start_time: int
    end_time: int


class VendorVisit(CasaModel):
    id: str
    type: VisitTypeField
    status: VendorVisitStatusField
    request: dict[str, Any] = Field(default_factory=dict)
    calendar_event: VendorVisitCalendarEvent | None = None
    vendors: list[Any] = Field(default_factory=list)
    task_items: list[Any] = Field(default_factory=list)
    invoices: list[Any] = Field(default_factory=list)
    purchases: list[Any] = Field(default_factory=list)
    can_add_remove_items: bool = False
    can_cancel: bool = False
    feedback: Any | None = None
    conversation: Any | None = None
