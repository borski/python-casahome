"""Casa AI reads only. Message and active-response schemas are UNVERIFIED.

Static message-part payloads are tagged unions with unresolved wire encoding.
They remain JSON values rather than guessed discriminated models.
"""

from pydantic import Field, JsonValue

from casahome.models._base import CasaModel
from casahome.models.images import MediaAttachment


class CasaAIConversation(CasaModel):
    id: str


class CasaAIStarterSuggestion(CasaModel):
    prompt: str
    system_image: str | None = None


class CasaAIMessagePart(CasaModel):
    id: str | None = None
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
    conversation: CasaAIConversation | None
    messages: CasaAIMessagesResponse
    active_response: CasaAIActiveResponse | None
    starter_suggestions: list[CasaAIStarterSuggestion]
    event_cursor: str | None = None
    send_to_human_target_message_id: str | None = None
