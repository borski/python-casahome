"""Provisional visit and conversation reads, with no call grants or controls.

Fields inferred from the app. Envelopes haven't been observed live.
Task-item and conversation-part unions stay opaque JSON, not guessed tags.
The older requests.VendorVisit stays unchanged for compatibility.
"""

from pydantic import JsonValue

from casahome.models._base import CasaModel
from casahome.models.images import MediaAttachment
from casahome.models.purchases import RequestPurchase
from casahome.models.requests import VendorVisitCalendarEvent


class MemberInvoicePreview(CasaModel):
    id: str
    vendor_name: str
    amount_display: str
    user_collection_status: str
    status: str


class VendorVisitMessagePreview(CasaModel):
    sender_name: str
    sent_at: int
    message: str


class VendorVisitRequestSummary(CasaModel):
    id: str
    type: str
    status: str
    title: str
    emoji: str
    has_unread_messages: bool
    message_preview: VendorVisitMessagePreview | None = None


class VisitDetailVendor(CasaModel):
    id: str
    display_name: str
    compact_display_name: str
    type: str
    image_url: str | None = None
    image_cache_key: str | None = None
    active_work_started_at: int | None = None


class VisitConversationWindow(CasaModel):
    state: str
    opens_at: int | None = None
    closes_at: int | None = None
    closed_reason: str | None = None


class VisitConversationLiveCall(CasaModel):
    call_id: str
    started_at: int
    caption: str


class VisitConversationCounterparty(CasaModel):
    user_id: str
    role: str
    vendor_id: str | None = None
    display_name: str
    avatar_url: str | None = None
    avatar_url_cache_key: str | None = None


class VisitConversationParticipant(VisitConversationCounterparty):
    is_me: bool


class VisitConversationLatestMessage(CasaModel):
    sender_display_name: str
    sent_at: int
    message: str


class VisitConversationSummary(CasaModel):
    thread_id: str | None = None
    window: VisitConversationWindow
    counterparties: list[VisitConversationCounterparty]
    live_call: VisitConversationLiveCall | None = None
    calls_enabled: bool | None = None
    unread_count: int
    latest_message: VisitConversationLatestMessage | None = None


class VisitConversationMessage(CasaModel):
    id: str
    thread_id: str
    created_at: int
    sender_role: str
    sender_user_id: str
    sender_display_name: str
    sender_avatar_url: str | None = None
    sender_avatar_url_cache_key: str | None = None
    is_mine: bool
    content: str | None = None
    attachments: list[MediaAttachment]
    parts: list[JsonValue]


class VisitConversation(CasaModel):
    visit_id: str
    thread_id: str | None = None
    window: VisitConversationWindow
    calls_enabled: bool | None = None
    live_call: VisitConversationLiveCall | None = None
    unread_count: int
    participants: list[VisitConversationParticipant]
    messages: list[VisitConversationMessage]
    event_cursor: str | None = None


class VisitCallParticipant(CasaModel):
    user_id: str
    role: str
    rang_at: int | None = None
    joined_at: int | None = None
    left_at: int | None = None


class VisitCall(CasaModel):
    id: str
    vendor_visit_id: str
    status: str
    started_by_user_id: str
    started_by_role: str
    started_at: int
    answered_at: int | None = None
    ended_at: int | None = None
    duration_seconds: int | None = None
    recorded: bool
    participants: list[VisitCallParticipant]


class VisitCallsResponse(CasaModel):
    calls: list[VisitCall]


class VendorVisitDetails(CasaModel):
    id: str
    type: str
    status: str
    request: VendorVisitRequestSummary
    calendar_event: VendorVisitCalendarEvent | None = None
    vendors: list[VisitDetailVendor]
    task_items: list[JsonValue]
    invoices: list[MemberInvoicePreview]
    purchases: list[RequestPurchase]
    can_add_remove_items: bool
    can_cancel: bool
    feedback: JsonValue = None
    conversation: VisitConversationSummary | None = None
