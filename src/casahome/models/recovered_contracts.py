"""Offline reconstructed codecs. Server acceptance and effects are UNVERIFIED.

Only statically joined scalar contracts are represented here. These models don't
authorize an action or imply that a successful HTTP status means success.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from casahome.models._base import CasaModel
from casahome.models.enums import RequestStatusField, RequestTypeField
from casahome.models.tasks import TaskDetails
from casahome.models.write_contracts import WRITE_TEXT_MAX_CHARS, _WriteModel

_Text = Annotated[StrictStr, Field(max_length=WRITE_TEXT_MAX_CHARS)]
_Name = Annotated[StrictStr, Field(min_length=1, max_length=256)]


class UpdateRequestDetailBody(_WriteModel):
    title: _Text | None = None
    read_state: Literal["read", "unread"] | None = None

    @model_validator(mode="after")
    def nonempty(self) -> UpdateRequestDetailBody:
        if self.title is None and self.read_state is None:
            raise ValueError("at least one request change is required")
        return self


class UpdateRequestDetailResponse(CasaModel):
    """Direct six-field result, distinct from the GET request thread."""

    id: StrictStr
    type: RequestTypeField
    status: RequestStatusField
    title: StrictStr
    emoji: StrictStr
    has_unread_messages: StrictBool


class DismissDocumentStructureSuggestionBody(_WriteModel):
    decision: Literal["dismissed"] = "dismissed"
    expected_values: list[_Text]


class UpdateTaskScalarBody(_WriteModel):
    """Attachment changes aren't supported. None means omit, never clear."""

    title: _Text | None = None
    description: _Text | None = None
    emoji: _Text | None = None

    @model_validator(mode="after")
    def nonempty(self) -> UpdateTaskScalarBody:
        if all(value is None for value in (self.title, self.description, self.emoji)):
            raise ValueError("at least one task change is required")
        return self


class UpdateTaskResponse(TaskDetails):
    """PATCH-only strict capability flags. Legacy task GET remains permissive."""

    can_schedule_handyman_vendor_visit: StrictBool
    can_chat_with_concierge: StrictBool
    can_edit: StrictBool
    can_delete: StrictBool


class TransferToConciergeResponse(CasaModel):
    request_id: StrictStr
    title: StrictStr
    message: StrictStr


class HomeDocumentDeleteResponse(CasaModel):
    deleted: StrictBool


class UpdateRoomProperty(_WriteModel):
    definition_id: _Name
    value: _Text | None = None


class UpdateRoomPropertiesBody(_WriteModel):
    props: list[UpdateRoomProperty]


class UpdateStoryBody(_WriteModel):
    name: _Text | None = None
    floor_number: StrictInt | None = None

    @model_validator(mode="after")
    def nonempty(self) -> UpdateStoryBody:
        if self.name is None and self.floor_number is None:
            raise ValueError("at least one story change is required")
        return self


class RetailerDiscount(CasaModel):
    id: StrictStr
    vendor_id: StrictStr
    retailer_name: StrictStr
    discount_headline: StrictStr
    sort_order: StrictInt
    logo_url: StrictStr | None = None
    logo_url_cache_key: StrictStr | None = None
    hero_image_url: StrictStr | None = None
    hero_image_url_cache_key: StrictStr | None = None
    discount_description: StrictStr | None = None
    discount_terms: StrictStr | None = None
    website_url: StrictStr | None = None
    return_window_days: StrictInt | None = None


class RetailerDiscountsResponse(CasaModel):
    data: list[RetailerDiscount]


class SupportRequestBody(_WriteModel):
    content: Annotated[StrictStr, Field(min_length=1, max_length=WRITE_TEXT_MAX_CHARS)]


class SupportRequestResponse(CasaModel):
    request_id: StrictStr


class VisitConversationReadResponse(CasaModel):
    ok: StrictBool
