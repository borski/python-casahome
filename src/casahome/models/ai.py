"""Casa AI messages, send/feedback responses, and thread.update payloads.

Message parts are a tagged union on ``type``. Live traffic (2026-10) showed
``text`` parts (``id``, ``text``) and ``data-todo`` parts, which carry a to-do
card the assistant created. Every part parses into ``CasaAIMessagePart``: the
``type`` tag is kept, ``text`` is typed, and any other payload keys stay in
``model_extra`` as JSON. Unknown part types parse the same way and never fail.
"""

from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, JsonValue, StrictBool, Tag

from casahome.models._base import CasaModel
from casahome.models.images import MediaAttachment

AI_PART_TEXT = "text"
AI_PART_DATA_TODO = "data-todo"
AI_CHANGE_MESSAGE_UPSERT = "message.upsert"


class CasaAIConversation(CasaModel):
    id: str


class CasaAIStarterSuggestion(CasaModel):
    prompt: str
    system_image: str | None = None


class CasaAIMessagePart(CasaModel):
    """One message part. Check ``type`` before reading ``text``.

    ``payload`` is the older static guess at the part body and stays for
    compatibility. Live parts put their fields at the top level, so
    ``data-todo`` content is in ``model_extra``.
    """

    type: str | None = None
    id: str | None = None
    text: str | None = None
    payload: JsonValue = None


class CasaAIMessageFeedback(CasaModel):
    rating: str | None = None


class CasaAIMessage(CasaModel):
    id: str | None = None
    content: str | None = None
    sender_role: str | None = None
    created_at: int | None = None
    parts: list[CasaAIMessagePart] = Field(default_factory=list)
    attachments: list[MediaAttachment] = Field(default_factory=list)
    feedback: CasaAIMessageFeedback | None = None


class CasaAIMessagesResponse(CasaModel):
    items: list[CasaAIMessage]
    next_cursor: str | None = None


class CasaAIActiveResponse(CasaModel):
    message_id: str | None = None
    status_message: str | None = None
    parts: list[CasaAIMessagePart] = Field(default_factory=list)


class CasaAIBootstrapResponse(CasaModel):
    """``event_cursor`` is an opaque resume token for ``casa_ai_events``.

    Store it and pass it back unchanged. Don't decode, build or edit cursors.
    """

    conversation: CasaAIConversation | None
    messages: CasaAIMessagesResponse
    active_response: CasaAIActiveResponse | None
    starter_suggestions: list[CasaAIStarterSuggestion]
    event_cursor: str | None = None
    send_to_human_target_message_id: str | None = None


class CasaAISendMessageResponse(CasaModel):
    """HTTP 202 body from sending a message. VERIFIED (live, 2026-10).

    ``member_message`` is the stored copy of what was sent. The assistant's
    reply arrives later on the event stream. ``active_response`` reports the
    in-progress reply (observed with a status message and no parts yet).
    """

    member_message: CasaAIMessage
    active_response: CasaAIActiveResponse | None = None


class CasaAIFeedbackResponse(CasaModel):
    """Body from rating a message. VERIFIED (live, 2026-10)."""

    success: StrictBool
    feedback: CasaAIMessageFeedback


class CasaAIMessageUpsertChange(CasaModel):
    """A message was added or replaced in the thread. VERIFIED (live, 2026-10)."""

    type: Literal["message.upsert"]
    message: CasaAIMessage


class CasaAIUnknownChange(CasaModel):
    """Any other change type. All fields are kept in ``model_extra``."""

    type: str | None = None


def _change_tag(value: Any) -> str:
    kind = value.get("type") if isinstance(value, dict) else getattr(value, "type", None)
    return "upsert" if kind == AI_CHANGE_MESSAGE_UPSERT else "unknown"


CasaAIThreadChange = Annotated[
    Annotated[CasaAIMessageUpsertChange, Tag("upsert")]
    | Annotated[CasaAIUnknownChange, Tag("unknown")],
    Discriminator(_change_tag),
]


class CasaAIThreadUpdate(CasaModel):
    """Parsed ``thread.update`` event data. VERIFIED (live, 2026-10).

    Observed with ``message.upsert`` changes for both member and concierge
    messages. ``cursor`` is opaque, like the bootstrap ``event_cursor``.
    """

    conversation_id: str | None = None
    cursor: str | None = None
    changes: list[CasaAIThreadChange] = Field(default_factory=list)
    active_response: CasaAIActiveResponse | None = None
    send_to_human_target_message_id: str | None = None
