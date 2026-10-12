"""Mostly provisional codecs reconstructed from concrete app encoders.

Recipient first/last-name creation and mailbox auto-archive with 30 or null
also match observed app traffic. Other operations and uncaptured variants remain
UNVERIFIED. Text and array bounds are SDK policy, not recovered server limits.
These types don't authorize writes. Unknown response extras follow the existing
CasaModel policy.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from casahome._common import _safe_id
from casahome.models._base import CasaModel
from casahome.models.mailbox import MailboxRecipient
from casahome.models.write_contracts import WRITE_TEXT_MAX_CHARS, _WriteModel

MAIL_WRITE_MAX_ITEMS = 100
"""SDK policy bound for capture upload IDs and paint room IDs."""

_Text = Annotated[StrictStr, Field(max_length=WRITE_TEXT_MAX_CHARS)]
_Id = Annotated[StrictStr, Field(min_length=1, max_length=2048), AfterValidator(_safe_id)]
_Ids = Annotated[list[_Id], Field(max_length=MAIL_WRITE_MAX_ITEMS)]
PackageDirectionInput = Literal["inbound", "outbound", "unknown"]
"""Recovered wire strings. Server acceptance of unknown remains UNVERIFIED."""


def _uploaded_image_path(value: str) -> str:
    """Accept relative upload object keys, never local paths or URL inputs.

    This is SDK policy, not a recovered server path grammar. A key's origin
    can't be authenticated offline. The API also requires a matching typed
    receipt supplied by the caller from the official package image upload.
    """
    if (
        not value
        or value.startswith(("/", "~"))
        or any(char in value for char in ("\\", ":", "?", "#", "%"))
        or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("package image path must be a relative official-upload object key")
    return value


_ImagePath = Annotated[_Text, AfterValidator(_uploaded_image_path)]


class AddMailboxRecipientRequest(_WriteModel):
    """None fields are omitted. Empty and mixed-name requests aren't forbidden.

    Name validation and person/business exclusivity aren't recovered. No kind,
    always_included or is_primary write fields were present in the builder.
    """

    first_name: _Text | None = None
    last_name: _Text | None = None
    business_name: _Text | None = None


class MailboxAutoArchiveRequest(_WriteModel):
    """Required nullable key. UI choices and server integer ranges are unknown."""

    mailbox_auto_archive_days: StrictInt | None


class TrackingNumberValidationRequest(_WriteModel):
    tracking_number: _Text


class AddPackageRequest(_WriteModel):
    """Carrier ID belongs in the route, not the request body."""

    tracking_number: _Text
    name: _Text
    direction: PackageDirectionInput


class UpdatePackageRequest(_WriteModel):
    """None is omitted. False and empty names are preserved.

    deleted=True may delete a package, not merely cancel pickup. No harmless
    cancellation meaning, clear behavior or combination rules are inferred.
    """

    archive: StrictBool | None = None
    deleted: StrictBool | None = None
    name: _Text | None = None
    direction: PackageDirectionInput | None = None


class CreatePackagePickupItemRequest(_WriteModel):
    """Image path must come from the official package image upload response.

    Optional strings are omitted when None. amazon_location is an open String
    input, not the response enum. There are no pickup times or slot IDs here.
    """

    carrier_id: _Id
    package_image_path: _ImagePath
    tracking_number: _Text | None = None
    qr_code: _Text | None = None
    amazon_location: _Text | None = None
    suggested_name: _Text | None = None


class UpdatePackageAutoArchiveRequest(_WriteModel):
    """Required nullable key, encoded even when None."""

    package_auto_archive_days: StrictInt | None


class CreateEntityRequest(_WriteModel):
    """Capture constructor only. No entity type, make, model or property inputs."""

    home_id: _Id
    room_id: _Id
    image_upload_ids: _Ids | None = None


class CreateLightingFixture(_WriteModel):
    entity_type_id: _Id
    image_upload_ids: _Ids | None = None


class CreateLightingBulb(_WriteModel):
    """kind is an open String. No associated-value tag encoding was recovered."""

    kind: _Text
    entity_type_id: _Id | None = None
    image_upload_ids: _Ids | None = None


class CreateLightingRequest(_WriteModel):
    room_id: _Id
    fixture: CreateLightingFixture
    bulb: CreateLightingBulb


class CreatePaintFromLibraryRequest(_WriteModel):
    """Only an integer color ID and room IDs were recovered. No extra props."""

    paint_color_id: StrictInt
    room_ids: _Ids


class _Receipt(CasaModel):
    """Strict known metadata with permissive unknown response extras."""

    model_config = ConfigDict(strict=True, revalidate_instances="always")


class MailboxRecipientResponse(_Receipt):
    """Required envelope reusing the existing recipient response model."""

    recipient: MailboxRecipient


class MailboxAutoArchiveResponse(_Receipt):
    success: StrictBool
    mailbox_auto_archive_days: StrictInt | None = None


class TrackingNumberValidationResponse(_Receipt):
    tracking_number: StrictStr
    valid: StrictBool
    carrier_matches: list[StrictStr]


class PackagePickupImageUploadResponse(_Receipt):
    """Metadata receipt only. No multipart transport, downloading or URL fetch.

    Callers must obtain this from the official package image upload. Constructing
    this model doesn't establish provenance or authorize a pickup. size units
    and accepted upload formats remain UNVERIFIED.
    """

    gcs_url: StrictStr
    thumbnail_url: StrictStr
    path: StrictStr
    mime_type: StrictStr
    size: StrictInt
    suggested_name: StrictStr | None = None


class UpdatePackageAutoArchiveResponse(_Receipt):
    success: StrictBool
    package_auto_archive_days: StrictInt | None = None


class CreateEntityResponse(_Receipt):
    entity_id: StrictStr
    message: StrictStr


class CreateLightingResponse(_Receipt):
    fixture_entity_id: StrictStr
    bulb_entity_id: StrictStr | None = None
    message: StrictStr


class CreatePaintFromLibraryResponse(_Receipt):
    entity_id: StrictStr
