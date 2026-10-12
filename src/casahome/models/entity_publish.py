"""Inventory publish and room rename contracts with scoped evidence.

``save_and_publish`` takes an optional make and an optional model, each a
catalog field selection. The app's ``CatalogFieldSelection`` has three cases:
existing ``{"id": ...}`` and new ``{"name": ...}`` have statically verified
encoding for both make and model. That isn't traffic verification of every
variant. In particular, model-ID traffic remains UNVERIFIED. The compiled clear
case encodes explicit null, but server clearing semantics remain UNVERIFIED,
so it isn't offered. SDK ``None`` means omission, not clear.
Editable properties remain UNVERIFIED on this route, so ``props`` must be empty.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import AfterValidator, Field, model_validator

from casahome.models._base import CasaModel
from casahome.models.home import EntityIdentity, EntityMake, EntityModel
from casahome.models.write_contracts import UpdateEntityProperty, _WriteModel

CATALOG_NAME_MAX_CHARS = 256
"""SDK cap on make/model names. Not a server limit, which is UNKNOWN."""

CATALOG_ID_MAX_CHARS = 128
"""SDK cap on catalog IDs. Observed IDs are UUIDs."""

ROOM_NAME_MAX_CHARS = 256
"""SDK cap on room names. Not a server limit, which is UNKNOWN."""


def _visible_text(value: str) -> str:
    """Reject blank and control-character text without trimming or normalizing.

    The message never echoes the value.
    """
    if not value.strip():
        raise ValueError("text must not be blank")
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise ValueError("text must not contain control characters")
    return value


_CatalogName = Annotated[
    str, Field(min_length=1, max_length=CATALOG_NAME_MAX_CHARS), AfterValidator(_visible_text)
]
_CatalogId = Annotated[
    str, Field(min_length=1, max_length=CATALOG_ID_MAX_CHARS, pattern=r"^[A-Za-z0-9._~-]+$")
]
_RoomName = Annotated[
    str, Field(min_length=1, max_length=ROOM_NAME_MAX_CHARS), AfterValidator(_visible_text)
]


class CatalogFieldId(_WriteModel):
    """Existing catalog entry. Static ``{"id": ...}`` encoding for either side.

    Model-ID traffic verification remains UNVERIFIED.
    """

    id: _CatalogId


class CatalogFieldName(_WriteModel):
    """Free-text name, sent as ``{"name": ...}`` for make or model.

    The server matches names against its catalog and may return a different
    canonical name. Unknown names fail with HTTP 400 ``CATALOG_MODEL_UNVERIFIED``.
    The name is sent as given, without trimming.
    """

    name: _CatalogName


class EntityModelName(CatalogFieldName):
    """Name-only model input kept for existing callers. Same as ``CatalogFieldName``."""


CatalogFieldSelection = CatalogFieldId | CatalogFieldName
"""Exactly one of ``{"id": ...}`` or ``{"name": ...}``. No clear variant."""


class SaveAndPublishEntityRequest(_WriteModel):
    """Optional make and model selections with an explicitly empty props list.

    ``None`` sides are omitted from the wire body. At least one side is required,
    since a props-only publish hasn't been observed. The property codec is
    static and UNVERIFIED on this route, so nonempty props are rejected.
    """

    make: CatalogFieldSelection | None = None
    model: CatalogFieldSelection | None = None
    props: list[UpdateEntityProperty] = Field(max_length=0)

    @model_validator(mode="after")
    def _require_a_selection(self) -> Self:
        if self.make is None and self.model is None:
            raise ValueError("make or model is required")
        return self


class SaveAndPublishEntityResponse(CasaModel):
    """VERIFIED populated response. Status seen as published, identity as verified.

    Observed identity: ``state="verified"``, null ``unverified_make`` and
    ``unverified_model``, and empty ``candidates``. Existing catalog/identity
    models preserve unknown response fields. Populated candidates and other
    status values remain UNVERIFIED. The compiled decoder permits missing or
    null make/model fields. Tolerating those shapes isn't live verification.
    The SDK's required entity_id, status and identity contract is retained.
    """

    entity_id: str
    status: str
    make: EntityMake | None = None
    model: EntityModel | None = None
    identity: EntityIdentity


class RenameRoomRequest(_WriteModel):
    """VERIFIED ``PATCH`` room body. Both keys are always sent."""

    room_type_id: _CatalogId
    name: _RoomName
