"""Mostly provisional single-attempt writes, with two captured mailbox contracts.

Recipient first/last-name creation and mailbox auto-archive with 30 or null
were observed in app traffic. The other 13 methods remain UNVERIFIED. No retry,
upload, forwarding, billing, shred/deposit or access-preference workflow is
added. Inputs are revalidated before I/O and response schema errors are scrubbed.
No method falls back to an untyped response dictionary.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from casahome._common import _parse, _write_home, _write_id, unverified
from casahome.client import CasaClient
from casahome.exceptions import CasaRequestError
from casahome.models.mail_workflows import (
    AddMailboxRecipientRequest,
    AddPackageRequest,
    CreateEntityRequest,
    CreateEntityResponse,
    CreateLightingRequest,
    CreateLightingResponse,
    CreatePackagePickupItemRequest,
    CreatePaintFromLibraryRequest,
    CreatePaintFromLibraryResponse,
    MailboxAutoArchiveRequest,
    MailboxAutoArchiveResponse,
    MailboxRecipientResponse,
    PackagePickupImageUploadResponse,
    TrackingNumberValidationRequest,
    TrackingNumberValidationResponse,
    UpdatePackageAutoArchiveRequest,
    UpdatePackageAutoArchiveResponse,
    UpdatePackageRequest,
)
from casahome.models.write_contracts import BasicMessageResponse


def _payload(
    schema: type[BaseModel], source: object, *, exclude_none: bool = True
) -> dict[str, Any]:
    """Revalidate strict instances directly, including nested copy/construct bypasses."""
    try:
        validated = schema.model_validate(source)
    except ValidationError as err:
        message = f"Invalid {schema.__name__} write body: {err.error_count()} validation error(s)"
    else:
        return validated.model_dump(mode="json", exclude_none=exclude_none)
    # Pydantic echoes inputs. Raise outside its handler to discard error context.
    raise CasaRequestError(message)


def _request_payload(body: BaseModel, schema: type[BaseModel]) -> dict[str, Any]:
    """Only the declared request model is supported, not permissive read models."""
    if not isinstance(body, schema):
        raise CasaRequestError(f"write body must be a {schema.__name__} request model")
    return _payload(schema, body)


class ProvisionalMailMixin:
    """Mostly provisional mail, package and narrow capture constructors.

    add_mailbox_recipient and update_mailbox_auto_archive have narrow contracts
    observed in app traffic. The other 13 methods have offline evidence only.
    Retry guarantees and uncaptured variants remain UNVERIFIED. Obtain approval
    before using any write. A failed attempt may already have acted.
    """

    client: CasaClient

    async def add_mailbox_recipient(
        self,
        home_id: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        business_name: str | None = None,
    ) -> MailboxRecipientResponse:
        """VERIFIED for first_name and last_name with business_name omitted.

        Observed POST /protected/home/{home_id}/mailbox/recipients with both name
        strings and no business_name key, answered HTTP 200 with a recipient
        envelope. Its recipient has id, kind, first_name, last_name, nullable
        business_name, always_included and is_primary boolean metadata.

        business_name writes, empty or partial names and validation rules remain
        UNVERIFIED. The SDK omits None and preserves empty strings. No name
        exclusivity or recipient kind input is inferred. One attempt, no retry.
        """
        path = f"{_write_home(home_id)}/mailbox/recipients"
        payload = _payload(
            AddMailboxRecipientRequest,
            {"first_name": first_name, "last_name": last_name, "business_name": business_name},
        )
        return _parse(MailboxRecipientResponse, await self.client.post(path, json=payload))

    @unverified
    async def remove_mailbox_recipient(
        self, home_id: str, recipient_id: str
    ) -> BasicMessageResponse:
        """Static bodyless DELETE. Restrictions and undo semantics are unknown."""
        path = f"{_write_home(home_id)}/mailbox/recipients/{_write_id(recipient_id)}"
        return _parse(BasicMessageResponse, await self.client.delete(path))

    async def update_mailbox_auto_archive(
        self, home_id: str, mailbox_auto_archive_days: int | None
    ) -> MailboxAutoArchiveResponse:
        """VERIFIED for mailbox_auto_archive_days=30 and None, encoded as null.

        Observed PATCH /protected/home/{home_id}/mailbox/preferences/auto_archive
        with the required mailbox_auto_archive_days key set to 30 or null,
        answered HTTP 200 with success: bool and the same integer/null value.

        Other day values remain UNVERIFIED. The SDK sends the required key even
        for None. UI choice mappings and physical-disposal effects aren't
        inferred. One attempt, no retry.
        """
        path = f"{_write_home(home_id)}/mailbox/preferences/auto_archive"
        payload = _payload(
            MailboxAutoArchiveRequest,
            {"mailbox_auto_archive_days": mailbox_auto_archive_days},
            exclude_none=False,
        )
        return _parse(MailboxAutoArchiveResponse, await self.client.patch(path, json=payload))

    @unverified
    async def mark_mail_item_read(self, home_id: str, mail_item_id: str) -> BasicMessageResponse:
        """Static bodyless POST to /read. Timestamp and badge effects are unknown."""
        path = f"{_write_home(home_id)}/mailbox/mail_items/{_write_id(mail_item_id)}/read"
        return _parse(BasicMessageResponse, await self.client.post(path))

    @unverified
    async def mark_mail_item_unread(self, home_id: str, mail_item_id: str) -> BasicMessageResponse:
        """Static bodyless POST to /unread. No timestamp semantics are inferred."""
        path = f"{_write_home(home_id)}/mailbox/mail_items/{_write_id(mail_item_id)}/unread"
        return _parse(BasicMessageResponse, await self.client.post(path))

    @unverified
    async def set_mail_item_archived(
        self, home_id: str, mail_item_id: str, archived: bool
    ) -> BasicMessageResponse:
        """Static bodyless POST to archive or unarchive. Archive isn't shredding."""
        if not isinstance(archived, bool):
            raise CasaRequestError("archived must be a bool")
        action = "archive" if archived else "unarchive"
        path = f"{_write_home(home_id)}/mailbox/mail_items/{_write_id(mail_item_id)}/{action}"
        return _parse(BasicMessageResponse, await self.client.post(path))

    @unverified
    async def validate_package_tracking_number(
        self, home_id: str, tracking_number: str
    ) -> TrackingNumberValidationResponse:
        """Static POST packages/validate_tracking_number. Not a side-effect guarantee."""
        path = f"{_write_home(home_id)}/packages/validate_tracking_number"
        payload = _payload(TrackingNumberValidationRequest, {"tracking_number": tracking_number})
        return _parse(TrackingNumberValidationResponse, await self.client.post(path, json=payload))

    @unverified
    async def add_tracked_package(
        self, home_id: str, carrier_id: str, body: AddPackageRequest
    ) -> BasicMessageResponse:
        """Static POST carrier/{id}/add_package with required tracking/name/direction.

        Wire directions are inbound, outbound and unknown. Server acceptance,
        duplicates and carrier compatibility remain unverified.
        """
        path = f"{_write_home(home_id)}/mail_packages/carrier/{_write_id(carrier_id)}/add_package"
        payload = _request_payload(body, AddPackageRequest)
        return _parse(BasicMessageResponse, await self.client.post(path, json=payload))

    @unverified
    async def update_package(
        self, home_id: str, package_id: str, body: UpdatePackageRequest
    ) -> BasicMessageResponse:
        """Static POST, not PATCH. Optional None fields are omitted.

        deleted=True may delete the record. This isn't a safe cancel operation.
        False and empty strings are sent unchanged. Null clearing is unsupported.
        """
        path = f"{_write_home(home_id)}/mail_packages/package/{_write_id(package_id)}/update"
        payload = _request_payload(body, UpdatePackageRequest)
        return _parse(BasicMessageResponse, await self.client.post(path, json=payload))

    @unverified
    async def requeue_package_pickup(self, home_id: str, package_id: str) -> BasicMessageResponse:
        """Static bodyless POST. Eligibility and next-window selection are unknown."""
        path = f"{_write_home(home_id)}/packages/{_write_id(package_id)}/pickup/requeue"
        return _parse(BasicMessageResponse, await self.client.post(path))

    @unverified
    async def create_package_pickup_item(
        self,
        home_id: str,
        body: CreatePackagePickupItemRequest,
        *,
        image_upload: PackagePickupImageUploadResponse,
    ) -> BasicMessageResponse:
        """Static POST packages/pickup/v3. Returns a message, not a package object.

        Require the caller's official package-upload receipt and matching path.
        Only the relative object key is sent, never receipt URLs or extras. This
        isn't cryptographic provenance verification. The SDK doesn't fetch an
        image or read a local file. Multipart upload is deliberately excluded.
        No pickup slot is selected. Carrier-specific requirements are unknown.
        """
        path = f"{_write_home(home_id)}/packages/pickup/v3"
        payload = _request_payload(body, CreatePackagePickupItemRequest)
        if not isinstance(image_upload, PackagePickupImageUploadResponse):
            raise CasaRequestError("image_upload must be an official package-upload receipt")
        receipt = _parse(PackagePickupImageUploadResponse, image_upload)
        if payload["package_image_path"] != receipt.path:
            raise CasaRequestError("package_image_path must match the official upload receipt")
        return _parse(BasicMessageResponse, await self.client.post(path, json=payload))

    @unverified
    async def set_package_auto_archive(
        self, home_id: str, package_auto_archive_days: int | None
    ) -> UpdatePackageAutoArchiveResponse:
        """Static PATCH. Always send the nullable key. No integer range is inferred."""
        path = f"{_write_home(home_id)}/packages/preferences/auto_archive"
        payload = _payload(
            UpdatePackageAutoArchiveRequest,
            {"package_auto_archive_days": package_auto_archive_days},
            exclude_none=False,
        )
        return _parse(UpdatePackageAutoArchiveResponse, await self.client.patch(path, json=payload))

    @unverified
    async def create_inventory_entity(
        self, home_id: str, body: CreateEntityRequest
    ) -> CreateEntityResponse:
        """Static PUT member-home/entity. Required home/room, optional upload IDs.

        SDK policy requires body and route home IDs to match. No custom make,
        model, entity type or props contract is inferred from this constructor.
        """
        path = f"{_write_home(home_id, member=True)}/entity"
        payload = _request_payload(body, CreateEntityRequest)
        if payload["home_id"] != home_id:
            raise CasaRequestError("body home_id must match the route home_id")
        return _parse(CreateEntityResponse, await self.client.put(path, json=payload))

    @unverified
    async def create_inventory_lighting(
        self, home_id: str, body: CreateLightingRequest
    ) -> CreateLightingResponse:
        """Static PUT member-home/entity/lighting with required fixture and bulb.

        The bulb kind remains an open String. No UI enum tags are invented.
        Optional nested fields are omitted, but explicit empty lists are sent.
        """
        path = f"{_write_home(home_id, member=True)}/entity/lighting"
        payload = _request_payload(body, CreateLightingRequest)
        return _parse(CreateLightingResponse, await self.client.put(path, json=payload))

    @unverified
    async def create_paint_from_library(
        self, home_id: str, body: CreatePaintFromLibraryRequest
    ) -> CreatePaintFromLibraryResponse:
        """Static POST entity/paint/from-library with integer color and room IDs.

        Empty arrays, multiple-room effects and downstream work are unverified.
        No boolean option, property payload or enum value was in this codec.
        """
        path = f"{_write_home(home_id)}/entity/paint/from-library"
        payload = _request_payload(body, CreatePaintFromLibraryRequest)
        return _parse(CreatePaintFromLibraryResponse, await self.client.post(path, json=payload))
