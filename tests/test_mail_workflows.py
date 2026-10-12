"""Synthetic offline codec tests. Even loopback networking is forbidden.

The real CasaClient request/error policy runs with fake auth and _send only.
No credentials, environment files, account data or server acceptance are used.
Parent API imports and public root exports are intentionally not tested here.
"""

from __future__ import annotations

import inspect
import json as jsonlib
import socket
import traceback
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast, get_type_hints

import aiohttp
import pytest
from pydantic import BaseModel, ValidationError

from casahome._common import is_unverified
from casahome.auth import FirebaseAuth
from casahome.client import CasaClient
from casahome.exceptions import (
    CasaApiError,
    CasaAuthError,
    CasaConnectionError,
    CasaRequestError,
    CasaResponseError,
)
from casahome.mail_workflows import ProvisionalMailMixin
from casahome.models import mail_workflows as codecs
from casahome.models.mailbox import MailboxRecipient
from casahome.models.write_contracts import BasicMessageResponse

HOME = "home-synthetic"
H = f"/protected/home/{HOME}"
MH = f"/protected/member/home/{HOME}"
CANARY = "SYNTHETIC-PRIVATE-VALUE"
IMAGE_PATH = "package-images/synthetic-upload"
IMAGE_RECEIPT: dict[str, Any] = {
    "gcs_url": "https://example.invalid/synthetic-image",
    "thumbnail_url": "https://example.invalid/synthetic-thumbnail",
    "path": IMAGE_PATH,
    "mime_type": "image/jpeg",
    "size": 8,
    "future_upload_extra": {"value": "not-a-write-field"},
}
RECIPIENT: dict[str, Any] = {
    "id": "recipient-synthetic",
    "kind": "future-kind",
    "always_included": True,
    "is_primary": None,
    "future_recipient_extra": {"value": None},
}


class OfflineAuth:
    """Fake token operations with counters, never a Firebase request."""

    def __init__(self) -> None:
        self.refreshes = 0
        self.invalidated: list[str] = []

    async def refresh(self) -> None:
        self.refreshes += 1

    def invalidate(self, token: str) -> None:
        self.invalidated.append(token)


@dataclass(frozen=True)
class Sent:
    method: str
    path: str
    body: Any
    params: Mapping[str, str] | None
    headers: Mapping[str, str] | None


class OfflineClient(CasaClient):
    """Exercise real request policy without constructing sessions or sockets."""

    def __init__(self) -> None:
        self.offline_auth = OfflineAuth()
        super().__init__(cast(aiohttp.ClientSession, None), cast(FirebaseAuth, self.offline_auth))
        self.calls: list[Sent] = []
        self.status = 200
        self.payload: Any = {"message": "synthetic status"}
        self.raw_body: str | None = None
        self.failure: Exception | None = None

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None,
        params: Mapping[str, str] | None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[int, str, str]:
        self.calls.append(Sent(method, path, deepcopy(json), params, extra_headers))
        if self.failure is not None:
            raise self.failure
        body = self.raw_body if self.raw_body is not None else jsonlib.dumps(self.payload)
        return self.status, body, "synthetic-token"


class TestApiMixin(ProvisionalMailMixin):
    __test__ = False

    def __init__(self, client: CasaClient) -> None:
        self.client = client


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("mail workflow tests forbid all networking")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def offline_client() -> OfflineClient:
    return OfflineClient()


@pytest.fixture
def mail_api(offline_client: OfflineClient) -> TestApiMixin:
    return TestApiMixin(offline_client)


@dataclass(frozen=True)
class WriteCase:
    name: str
    method: str
    path: str
    kwargs: dict[str, Any]
    body: dict[str, Any] | None
    response_model: type[BaseModel] = BasicMessageResponse
    response: dict[str, Any] | None = None
    request_model: type[BaseModel] | None = None

    def arguments(self) -> dict[str, Any]:
        kwargs = deepcopy(self.kwargs)
        if self.request_model is not None:
            kwargs["body"] = self.request_model.model_validate(self.body)
        if self.name == "create_package_pickup_item":
            kwargs["image_upload"] = codecs.PackagePickupImageUploadResponse.model_validate(
                IMAGE_RECEIPT
            )
        return kwargs


CASES = [
    WriteCase(
        "add_mailbox_recipient",
        "POST",
        f"{H}/mailbox/recipients",
        {},
        {},
        codecs.MailboxRecipientResponse,
        {"recipient": RECIPIENT},
    ),
    WriteCase(
        "remove_mailbox_recipient",
        "DELETE",
        f"{H}/mailbox/recipients/recipient-synthetic",
        {"recipient_id": "recipient-synthetic"},
        None,
    ),
    WriteCase(
        "update_mailbox_auto_archive",
        "PATCH",
        f"{H}/mailbox/preferences/auto_archive",
        {"mailbox_auto_archive_days": None},
        {"mailbox_auto_archive_days": None},
        codecs.MailboxAutoArchiveResponse,
        {"success": True},
    ),
    WriteCase(
        "mark_mail_item_read",
        "POST",
        f"{H}/mailbox/mail_items/mail-synthetic/read",
        {"mail_item_id": "mail-synthetic"},
        None,
    ),
    WriteCase(
        "mark_mail_item_unread",
        "POST",
        f"{H}/mailbox/mail_items/mail-synthetic/unread",
        {"mail_item_id": "mail-synthetic"},
        None,
    ),
    WriteCase(
        "set_mail_item_archived",
        "POST",
        f"{H}/mailbox/mail_items/mail-synthetic/archive",
        {"mail_item_id": "mail-synthetic", "archived": True},
        None,
    ),
    WriteCase(
        "validate_package_tracking_number",
        "POST",
        f"{H}/packages/validate_tracking_number",
        {"tracking_number": "synthetic-tracking"},
        {"tracking_number": "synthetic-tracking"},
        codecs.TrackingNumberValidationResponse,
        {"tracking_number": "normalized-synthetic", "valid": False, "carrier_matches": []},
    ),
    WriteCase(
        "add_tracked_package",
        "POST",
        f"{H}/mail_packages/carrier/carrier-synthetic/add_package",
        {"carrier_id": "carrier-synthetic"},
        {"tracking_number": "synthetic-tracking", "name": "", "direction": "outbound"},
        request_model=codecs.AddPackageRequest,
    ),
    WriteCase(
        "update_package",
        "POST",
        f"{H}/mail_packages/package/package-synthetic/update",
        {"package_id": "package-synthetic"},
        {},
        request_model=codecs.UpdatePackageRequest,
    ),
    WriteCase(
        "requeue_package_pickup",
        "POST",
        f"{H}/packages/package-synthetic/pickup/requeue",
        {"package_id": "package-synthetic"},
        None,
    ),
    WriteCase(
        "create_package_pickup_item",
        "POST",
        f"{H}/packages/pickup/v3",
        {},
        {"carrier_id": "carrier-synthetic", "package_image_path": IMAGE_PATH},
        request_model=codecs.CreatePackagePickupItemRequest,
    ),
    WriteCase(
        "set_package_auto_archive",
        "PATCH",
        f"{H}/packages/preferences/auto_archive",
        {"package_auto_archive_days": None},
        {"package_auto_archive_days": None},
        codecs.UpdatePackageAutoArchiveResponse,
        {"success": False},
    ),
    WriteCase(
        "create_inventory_entity",
        "PUT",
        f"{MH}/entity",
        {},
        {"home_id": HOME, "room_id": "room-synthetic"},
        codecs.CreateEntityResponse,
        {"entity_id": "entity-synthetic", "message": "created"},
        codecs.CreateEntityRequest,
    ),
    WriteCase(
        "create_inventory_lighting",
        "PUT",
        f"{MH}/entity/lighting",
        {},
        {
            "room_id": "room-synthetic",
            "fixture": {"entity_type_id": "fixture-type"},
            "bulb": {"kind": "synthetic-open-kind"},
        },
        codecs.CreateLightingResponse,
        {"fixture_entity_id": "fixture-synthetic", "message": "created"},
        codecs.CreateLightingRequest,
    ),
    WriteCase(
        "create_paint_from_library",
        "POST",
        f"{H}/entity/paint/from-library",
        {},
        {"paint_color_id": 17, "room_ids": []},
        codecs.CreatePaintFromLibraryResponse,
        {"entity_id": "paint-synthetic"},
        codecs.CreatePaintFromLibraryRequest,
    ),
]
CASE_BY_NAME = {case.name: case for case in CASES}
VERIFIED_METHODS = frozenset({"add_mailbox_recipient", "update_mailbox_auto_archive"})
REQUEST_MODELS = (
    codecs.AddMailboxRecipientRequest,
    codecs.MailboxAutoArchiveRequest,
    codecs.TrackingNumberValidationRequest,
    codecs.AddPackageRequest,
    codecs.UpdatePackageRequest,
    codecs.CreatePackagePickupItemRequest,
    codecs.UpdatePackageAutoArchiveRequest,
    codecs.CreateEntityRequest,
    codecs.CreateLightingFixture,
    codecs.CreateLightingBulb,
    codecs.CreateLightingRequest,
    codecs.CreatePaintFromLibraryRequest,
)


async def invoke(
    api: TestApiMixin, case: WriteCase, *, home_id: str = HOME, **overrides: Any
) -> BaseModel:
    kwargs = case.arguments()
    kwargs.update(overrides)
    result: BaseModel = await getattr(api, case.name)(home_id, **kwargs)
    return result


def assert_scrubbed(error: Exception) -> None:
    assert error.__context__ is None
    assert error.__cause__ is None
    assert CANARY not in str(error)
    assert CANARY not in repr(error)
    assert CANARY not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_all_public_methods_are_typed_and_match_evidence(case: WriteCase) -> None:
    method = getattr(ProvisionalMailMixin, case.name)
    assert inspect.iscoroutinefunction(method)
    verified = case.name in VERIFIED_METHODS
    assert is_unverified(method) is not verified
    doc = method.__doc__ or ""
    assert doc.startswith("VERIFIED" if verified else "UNVERIFIED")
    assert ("observed" if verified else "static") in doc.lower()
    if verified:
        assert "UNVERIFIED" in doc  # Uncaptured variants remain provisional.
    hints = get_type_hints(method)
    assert hints["home_id"] is str
    assert hints["return"] is case.response_model
    assert all(name == "self" or name in hints for name in inspect.signature(method).parameters)
    if case.request_model is not None:
        assert hints["body"] is case.request_model


def test_mixin_contract_and_exclusions() -> None:
    assert get_type_hints(ProvisionalMailMixin)["client"] is CasaClient
    public = {name for name in vars(ProvisionalMailMixin) if not name.startswith("_")}
    assert public == set(CASE_BY_NAME)
    marked = {name for name in public if is_unverified(getattr(ProvisionalMailMixin, name))}
    assert marked == public - VERIFIED_METHODS
    assert len(marked) == 13
    assert codecs.MailboxRecipientResponse.model_fields["recipient"].annotation is MailboxRecipient


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_exact_wire_and_typed_receipts(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase
) -> None:
    offline_client.payload = {
        **(case.response or {"message": "synthetic status"}),
        "future_receipt": {"status": "future-status"},
    }
    result = await invoke(mail_api, case)
    assert type(result) is case.response_model
    assert result.model_extra == {"future_receipt": {"status": "future-status"}}
    if case.name == "add_mailbox_recipient":
        assert isinstance(result, codecs.MailboxRecipientResponse)
        assert type(result.recipient) is MailboxRecipient
        assert result.recipient.kind == "future-kind"
        assert result.recipient.model_extra == {"future_recipient_extra": {"value": None}}
    (call,) = offline_client.calls
    assert (call.method, call.path, call.body) == (case.method, case.path, case.body)
    assert call.params is None and call.headers is None
    assert offline_client.offline_auth.refreshes == 1


@pytest.mark.parametrize("value", [None, 0, -3, 7, 30])
@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("update_mailbox_auto_archive", "mailbox_auto_archive_days"),
        ("set_package_auto_archive", "package_auto_archive_days"),
    ],
)
async def test_auto_archive_explicit_null_and_strict_integer(
    mail_api: TestApiMixin, offline_client: OfflineClient, name: str, key: str, value: int | None
) -> None:
    offline_client.payload = {"success": True, key: value}
    overrides: dict[str, Any] = {key: value}
    result = await invoke(mail_api, CASE_BY_NAME[name], **overrides)
    assert offline_client.calls[0].body == {key: value}
    assert getattr(result, key) == value


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"first_name": None, "last_name": None, "business_name": None}, {}),
        (
            {"first_name": "", "last_name": "  preserved  "},
            {"first_name": "", "last_name": "  preserved  "},
        ),
        (
            {"first_name": "person", "business_name": "business"},
            {"first_name": "person", "business_name": "business"},
        ),
    ],
)
async def test_recipient_omission_and_no_invented_exclusivity(
    mail_api: TestApiMixin,
    offline_client: OfflineClient,
    data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    offline_client.payload = {"recipient": RECIPIENT}
    await invoke(mail_api, CASE_BY_NAME["add_mailbox_recipient"], **data)
    assert offline_client.calls[0].body == expected


async def test_observed_recipient_contract_with_synthetic_names(
    mail_api: TestApiMixin, offline_client: OfflineClient
) -> None:
    """Exercise the captured shape, never captured values or a live request."""
    names = {"first_name": "Example", "last_name": "Person"}
    recipient = {
        "id": "recipient-synthetic",
        "kind": "synthetic-kind",
        **names,
        "business_name": None,
        "always_included": True,
        "is_primary": False,
    }
    offline_client.payload = {"recipient": recipient}
    result = await mail_api.add_mailbox_recipient(HOME, **names)
    assert result.recipient.model_dump() == recipient
    (call,) = offline_client.calls
    assert (call.method, call.path, call.body) == ("POST", f"{H}/mailbox/recipients", names)
    assert "business_name" not in call.body
    assert offline_client.offline_auth.refreshes == 1


@pytest.mark.parametrize("archived", [True, False])
async def test_archive_boolean_selects_bodyless_action(
    mail_api: TestApiMixin, offline_client: OfflineClient, archived: bool
) -> None:
    await invoke(mail_api, CASE_BY_NAME["set_mail_item_archived"], archived=archived)
    action = "archive" if archived else "unarchive"
    assert offline_client.calls[0].path.endswith(f"/{action}")
    assert offline_client.calls[0].body is None


@pytest.mark.parametrize("direction", ["inbound", "outbound", "unknown"])
async def test_all_recovered_direction_wire_strings(
    mail_api: TestApiMixin, offline_client: OfflineClient, direction: str
) -> None:
    body = codecs.AddPackageRequest.model_validate(
        {"tracking_number": "synthetic", "name": "", "direction": direction}
    )
    await invoke(mail_api, CASE_BY_NAME["add_tracked_package"], body=body)
    assert offline_client.calls[0].body["direction"] == direction
    assert "carrier_id" not in offline_client.calls[0].body


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"archive": None, "deleted": None, "name": None, "direction": None}, {}),
        (
            {"archive": False, "deleted": False, "name": ""},
            {"archive": False, "deleted": False, "name": ""},
        ),
        ({"deleted": True}, {"deleted": True}),
        ({"archive": True, "direction": "unknown"}, {"archive": True, "direction": "unknown"}),
    ],
)
async def test_package_updates_omit_none_without_cancel_alias(
    mail_api: TestApiMixin,
    offline_client: OfflineClient,
    data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    await invoke(
        mail_api,
        CASE_BY_NAME["update_package"],
        body=codecs.UpdatePackageRequest.model_validate(data),
    )
    assert offline_client.calls[0].body == expected
    assert not hasattr(mail_api, "cancel_package_pickup")


@pytest.mark.parametrize("optional_value", [None, "", "synthetic-open-string"])
async def test_pickup_option_strings_and_receipt_extras_not_sent(
    mail_api: TestApiMixin, offline_client: OfflineClient, optional_value: str | None
) -> None:
    keys = ("tracking_number", "qr_code", "amazon_location", "suggested_name")
    required = {"carrier_id": "carrier-synthetic", "package_image_path": IMAGE_PATH}
    data = {**required, **dict.fromkeys(keys, optional_value)}
    body = codecs.CreatePackagePickupItemRequest.model_validate(data)
    await invoke(mail_api, CASE_BY_NAME["create_package_pickup_item"], body=body)
    expected = required if optional_value is None else data
    assert offline_client.calls[0].body == expected


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/local/image",
        "~/image",
        "./image",
        "../image",
        "images/../image",
        "file:///local/image",
        "https://example.invalid/image",
        "//example.invalid/image",
        "C:\\image",
        "images\\image",
        "images//image",
        "images/image\n",
        "images/image\x7f",
        "images/image?query",
        "images/image#fragment",
        "images/%2e%2e/image",
    ],
)
async def test_pickup_image_inputs_are_not_local_paths_or_urls(
    mail_api: TestApiMixin, offline_client: OfflineClient, path: str
) -> None:
    body = codecs.CreatePackagePickupItemRequest.model_construct(
        carrier_id="carrier-synthetic", package_image_path=path
    )
    with pytest.raises(CasaRequestError):
        await invoke(mail_api, CASE_BY_NAME["create_package_pickup_item"], body=body)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("receipt", [None, {}, IMAGE_PATH, IMAGE_RECEIPT])
async def test_pickup_requires_typed_official_receipt(
    mail_api: TestApiMixin, offline_client: OfflineClient, receipt: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await invoke(mail_api, CASE_BY_NAME["create_package_pickup_item"], image_upload=receipt)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


async def test_pickup_path_must_match_receipt(
    mail_api: TestApiMixin, offline_client: OfflineClient
) -> None:
    receipt = codecs.PackagePickupImageUploadResponse.model_validate(
        {**IMAGE_RECEIPT, "path": "package-images/different-upload"}
    )
    with pytest.raises(CasaRequestError) as caught:
        await invoke(mail_api, CASE_BY_NAME["create_package_pickup_item"], image_upload=receipt)
    assert_scrubbed(caught.value)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


async def test_copied_receipt_is_revalidated_before_io(
    mail_api: TestApiMixin, offline_client: OfflineClient
) -> None:
    receipt = codecs.PackagePickupImageUploadResponse.model_validate(IMAGE_RECEIPT).model_copy(
        update={"path": {"value": CANARY}}
    )
    with pytest.raises(CasaResponseError) as caught:
        await invoke(mail_api, CASE_BY_NAME["create_package_pickup_item"], image_upload=receipt)
    assert_scrubbed(caught.value)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("uploads", [None, [], ["upload-synthetic"]])
async def test_capture_upload_ids_omit_none_but_keep_empty_lists(
    mail_api: TestApiMixin, offline_client: OfflineClient, uploads: list[str] | None
) -> None:
    offline_client.payload = {"entity_id": "entity-synthetic", "message": "created"}
    data = {"home_id": HOME, "room_id": "room-synthetic", "image_upload_ids": uploads}
    body = codecs.CreateEntityRequest.model_validate(data)
    await invoke(mail_api, CASE_BY_NAME["create_inventory_entity"], body=body)
    expected: dict[str, Any] = {"home_id": HOME, "room_id": "room-synthetic"}
    if uploads is not None:
        expected["image_upload_ids"] = uploads
    assert offline_client.calls[0].body == expected


async def test_entity_route_and_body_home_must_match(
    mail_api: TestApiMixin, offline_client: OfflineClient
) -> None:
    body = codecs.CreateEntityRequest(home_id="another-home", room_id="room-synthetic")
    with pytest.raises(CasaRequestError):
        await invoke(mail_api, CASE_BY_NAME["create_inventory_entity"], body=body)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


async def test_nested_lighting_wire_fields_without_invented_tags(
    mail_api: TestApiMixin, offline_client: OfflineClient
) -> None:
    offline_client.payload = {
        "fixture_entity_id": "fixture-synthetic",
        "bulb_entity_id": "bulb-synthetic",
        "message": "ok",
    }
    data = {
        "room_id": "room-synthetic",
        "fixture": {"entity_type_id": "fixture-type", "image_upload_ids": []},
        "bulb": {
            "kind": "arbitrary-string",
            "entity_type_id": "bulb-type",
            "image_upload_ids": ["upload-synthetic"],
        },
    }
    result = await invoke(
        mail_api,
        CASE_BY_NAME["create_inventory_lighting"],
        body=codecs.CreateLightingRequest.model_validate(data),
    )
    assert offline_client.calls[0].body == data
    assert isinstance(result, codecs.CreateLightingResponse)
    assert result.bulb_entity_id == "bulb-synthetic"


@pytest.mark.parametrize("model", REQUEST_MODELS)
def test_strict_request_config(model: type[BaseModel]) -> None:
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["strict"] is True
    assert model.model_config["validate_assignment"] is True
    assert model.model_config["revalidate_instances"] == "always"
    assert model.model_json_schema()["additionalProperties"] is False


INVALID_REQUESTS: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (codecs.AddMailboxRecipientRequest, {"kind": "person"}),
    (codecs.AddMailboxRecipientRequest, {"always_included": True}),
    (codecs.AddMailboxRecipientRequest, {"is_primary": True}),
    (codecs.AddMailboxRecipientRequest, {"first_name": 1}),
    (codecs.MailboxAutoArchiveRequest, {}),
    (codecs.MailboxAutoArchiveRequest, {"mailbox_auto_archive_days": True}),
    (codecs.MailboxAutoArchiveRequest, {"mailbox_auto_archive_days": "7"}),
    (codecs.UpdatePackageAutoArchiveRequest, {}),
    (codecs.UpdatePackageAutoArchiveRequest, {"package_auto_archive_days": 7.0}),
    (codecs.TrackingNumberValidationRequest, {}),
    (codecs.TrackingNumberValidationRequest, {"tracking_number": 123}),
    (
        codecs.AddPackageRequest,
        {"tracking_number": "synthetic", "name": "", "direction": "incoming"},
    ),
    (codecs.AddPackageRequest, {"tracking_number": "synthetic", "direction": "inbound"}),
    (codecs.UpdatePackageRequest, {"archive": 1}),
    (codecs.UpdatePackageRequest, {"deleted": "false"}),
    (codecs.UpdatePackageRequest, {"name": False}),
    (codecs.UpdatePackageRequest, {"direction": "outBound"}),
    (codecs.CreatePackagePickupItemRequest, {"carrier_id": "carrier-synthetic"}),
    (codecs.CreatePackagePickupItemRequest, {"package_image_path": IMAGE_PATH}),
    (
        codecs.CreatePackagePickupItemRequest,
        {"carrier_id": "carrier-synthetic", "package_image_path": IMAGE_PATH, "slot_id": "slot"},
    ),
    (
        codecs.CreatePackagePickupItemRequest,
        {"carrier_id": "carrier-synthetic", "package_image_path": IMAGE_PATH, "amazon_location": 1},
    ),
    (codecs.CreateEntityRequest, {"home_id": HOME, "room_id": "room", "make_id": "make"}),
    (codecs.CreateEntityRequest, {"home_id": HOME, "room_id": "room", "model": {"name": "x"}}),
    (codecs.CreateEntityRequest, {"home_id": HOME, "room_id": "room", "entity_type_id": "type"}),
    (codecs.CreateEntityRequest, {"home_id": HOME, "room_id": "room", "image_upload_ids": "id"}),
    (codecs.CreateEntityRequest, {"home_id": HOME, "room_id": "room", "image_upload_ids": ("id",)}),
    (codecs.CreateEntityRequest, {"home_id": HOME, "room_id": "room", "image_upload_ids": [1]}),
    (codecs.CreateLightingRequest, {"room_id": "room", "fixture": {"entity_type_id": "type"}}),
    (codecs.CreateLightingFixture, {"entity_type_id": "type", "model_id": "model"}),
    (codecs.CreateLightingBulb, {"kind": "synthetic", "new": {"name": "invented"}}),
    (codecs.CreateLightingBulb, {"kind": 1}),
    (codecs.CreatePaintFromLibraryRequest, {"paint_color_id": True, "room_ids": []}),
    (codecs.CreatePaintFromLibraryRequest, {"paint_color_id": "17", "room_ids": []}),
    (codecs.CreatePaintFromLibraryRequest, {"paint_color_id": 17, "room_ids": "room"}),
    (codecs.CreatePaintFromLibraryRequest, {"paint_color_id": 17, "room_ids": [], "props": []}),
]


@pytest.mark.parametrize(("model", "data"), INVALID_REQUESTS)
def test_invalid_request_shapes(model: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize(
    "case", [case for case in CASES if case.request_model is not None], ids=lambda case: case.name
)
@pytest.mark.parametrize("bypass", ["copy-extra", "dict-extra", "construct-invalid"])
async def test_request_bypass_revalidation_prevents_io(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, bypass: str
) -> None:
    body = case.arguments()["body"]
    if bypass == "copy-extra":
        body = body.model_copy(update={"unrecovered": CANARY})
    elif bypass == "dict-extra":
        body.__dict__["unrecovered"] = CANARY
    else:
        assert case.request_model is not None
        data = body.model_dump(mode="python")
        key = next(iter(case.request_model.model_fields))
        data[key] = {"value": CANARY}
        body = case.request_model.model_construct(**data)
    with pytest.raises(CasaRequestError) as caught:
        await invoke(mail_api, case, body=body)
    assert_scrubbed(caught.value)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("field", ["fixture", "bulb"])
@pytest.mark.parametrize("bypass", ["extra", "invalid"])
async def test_nested_lighting_instances_revalidated(
    mail_api: TestApiMixin, offline_client: OfflineClient, field: str, bypass: str
) -> None:
    case = CASE_BY_NAME["create_inventory_lighting"]
    body = case.arguments()["body"]
    child = getattr(body, field)
    update = (
        {"unrecovered": CANARY}
        if bypass == "extra"
        else {"entity_type_id" if field == "fixture" else "kind": {"value": CANARY}}
    )
    body.__dict__[field] = child.model_copy(update=update)
    with pytest.raises(CasaRequestError) as caught:
        await invoke(mail_api, case, body=body)
    assert_scrubbed(caught.value)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize(
    "case", [case for case in CASES if case.request_model is not None], ids=lambda case: case.name
)
@pytest.mark.parametrize("body", [None, {}, [], "synthetic"])
async def test_nonmodel_request_rejected_safely(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, body: Any
) -> None:
    with pytest.raises(CasaRequestError) as caught:
        await invoke(mail_api, case, body=body)
    assert_scrubbed(caught.value)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        ".",
        "..",
        "a/b",
        "a\\b",
        "a?b",
        "a#b",
        "a%2Fb",
        "a b",
        "a\n",
        "é",
        "x" * 2049,
        None,
        False,
        {},
    ],
)
async def test_invalid_home_before_auth_or_io(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, bad_id: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await invoke(mail_api, case, home_id=bad_id)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if any(key.endswith("_id") for key in case.kwargs)],
    ids=lambda case: case.name,
)
@pytest.mark.parametrize("bad_id", ["a/b", "a%2Fb", "a\x00", "..", True])
async def test_invalid_route_resource_before_auth_or_io(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, bad_id: Any
) -> None:
    key = next(key for key in case.kwargs if key.endswith("_id"))
    with pytest.raises(CasaRequestError):
        await invoke(mail_api, case, **{key: bad_id})
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize(
    ("name", "key", "bad"),
    [
        (name, key, bad)
        for name, key in (
            ("update_mailbox_auto_archive", "mailbox_auto_archive_days"),
            ("set_package_auto_archive", "package_auto_archive_days"),
            ("set_mail_item_archived", "archived"),
        )
        for bad in (
            [0, 1, "false", None, 7.0, [], {}]
            if key == "archived"
            else [True, False, "false", "7", 7.0, [], {}]
        )
    ],
)
async def test_primitive_flags_and_days_strict_before_io(
    mail_api: TestApiMixin, offline_client: OfflineClient, name: str, key: str, bad: Any
) -> None:
    with pytest.raises(CasaRequestError):
        await invoke(mail_api, CASE_BY_NAME[name], **{key: bad})
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("name", ["add_mailbox_recipient", "validate_package_tracking_number"])
async def test_primitive_text_errors_scrubbed(
    mail_api: TestApiMixin, offline_client: OfflineClient, name: str
) -> None:
    key = "first_name" if name == "add_mailbox_recipient" else "tracking_number"
    overrides: dict[str, Any] = {key: {"value": CANARY}}
    with pytest.raises(CasaRequestError) as caught:
        await invoke(mail_api, CASE_BY_NAME[name], **overrides)
    assert_scrubbed(caught.value)
    assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("name", ["add_mailbox_recipient", "validate_package_tracking_number"])
@pytest.mark.parametrize("size", [10_000, 10_001])
async def test_primitive_text_policy_bound_before_auth_or_io(
    mail_api: TestApiMixin, offline_client: OfflineClient, name: str, size: int
) -> None:
    key = "first_name" if name == "add_mailbox_recipient" else "tracking_number"
    case = CASE_BY_NAME[name]
    offline_client.payload = case.response
    overrides: dict[str, Any] = {key: "x" * size}
    if size == 10_000:
        await invoke(mail_api, case, **overrides)
        assert len(offline_client.calls) == 1
    else:
        with pytest.raises(CasaRequestError):
            await invoke(mail_api, case, **overrides)
        assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


TEXT_FIELDS: list[tuple[type[BaseModel], dict[str, Any], str]] = [
    (codecs.AddMailboxRecipientRequest, {}, key)
    for key in ("first_name", "last_name", "business_name")
] + [
    (codecs.TrackingNumberValidationRequest, {}, "tracking_number"),
    *[
        (
            codecs.AddPackageRequest,
            {"tracking_number": "synthetic", "name": "", "direction": "inbound"},
            key,
        )
        for key in ("tracking_number", "name")
    ],
    (codecs.UpdatePackageRequest, {}, "name"),
    *[
        (
            codecs.CreatePackagePickupItemRequest,
            {"carrier_id": "carrier-synthetic", "package_image_path": IMAGE_PATH},
            key,
        )
        for key in (
            "package_image_path",
            "tracking_number",
            "qr_code",
            "amazon_location",
            "suggested_name",
        )
    ],
    (codecs.CreateLightingBulb, {}, "kind"),
]


@pytest.mark.parametrize(("model", "data", "key"), TEXT_FIELDS)
def test_every_free_text_field_has_sdk_policy_bound(
    model: type[BaseModel], data: dict[str, Any], key: str
) -> None:
    assert model.model_validate({**data, key: "x" * 10_000})
    with pytest.raises(ValidationError):
        model.model_validate({**data, key: "x" * 10_001})


@pytest.mark.parametrize(
    "name", ["create_inventory_entity", "create_inventory_lighting", "create_paint_from_library"]
)
@pytest.mark.parametrize("size", [100, 101])
async def test_capture_arrays_revalidated_with_sdk_policy_bound(
    mail_api: TestApiMixin, offline_client: OfflineClient, name: str, size: int
) -> None:
    case = CASE_BY_NAME[name]
    kwargs = case.arguments()
    body = kwargs["body"]
    if name == "create_inventory_entity":
        body.image_upload_ids = []
        target = body.image_upload_ids
    elif name == "create_inventory_lighting":
        body.bulb.image_upload_ids = []
        target = body.bulb.image_upload_ids
    else:
        target = body.room_ids
    target.extend(["id-synthetic"] * size)
    offline_client.payload = case.response
    if size == 100:
        await invoke(mail_api, case, body=body)
        assert len(offline_client.calls) == 1
    else:
        with pytest.raises(CasaRequestError):
            await invoke(mail_api, case, body=body)
        assert offline_client.calls == [] and offline_client.offline_auth.refreshes == 0


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("status", [401, 400, 503])
async def test_single_attempt_including_401(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, status: int
) -> None:
    offline_client.status = status
    offline_client.payload = {"error": {"code": "synthetic-failure"}}
    expected = CasaAuthError if status == 401 else CasaApiError
    with pytest.raises(expected):
        await invoke(mail_api, case)
    assert len(offline_client.calls) == 1
    assert offline_client.offline_auth.refreshes == 1
    assert offline_client.offline_auth.invalidated == (["synthetic-token"] if status == 401 else [])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("error", [CasaConnectionError("synthetic timeout"), TimeoutError()])
async def test_unknown_results_never_retry(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, error: Exception
) -> None:
    offline_client.failure = error
    with pytest.raises(type(error)):
        await invoke(mail_api, case)
    assert len(offline_client.calls) == 1 and offline_client.offline_auth.refreshes == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("response", [{}, None, [], "synthetic", False, {"success": True}])
async def test_receipts_never_fall_back_to_raw_dictionary(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, response: Any
) -> None:
    if response == {"success": True} and case.name in {
        "update_mailbox_auto_archive",
        "set_package_auto_archive",
    }:
        response = {"success": "true"}
    offline_client.payload = response
    with pytest.raises(CasaResponseError) as caught:
        await invoke(mail_api, case)
    assert_scrubbed(caught.value)
    assert len(offline_client.calls) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_response_schema_errors_scrub_private_data(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase
) -> None:
    response = deepcopy(case.response or {"message": "synthetic status"})
    key = next(iter(response))
    response[key] = {"value": CANARY}
    offline_client.payload = response
    with pytest.raises(CasaResponseError) as caught:
        await invoke(mail_api, case)
    assert_scrubbed(caught.value)
    assert len(offline_client.calls) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("status", [200, 500])
async def test_http_policy_scrubs_raw_non_json_without_retry(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase, status: int
) -> None:
    offline_client.status = status
    offline_client.raw_body = f"<html>{CANARY}</html>"
    with pytest.raises(CasaApiError) as caught:
        await invoke(mail_api, case)
    assert_scrubbed(caught.value)
    assert caught.value.display_message == ""
    assert len(offline_client.calls) == 1


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_structured_http_errors_keep_existing_client_contract(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase
) -> None:
    offline_client.status = 400
    offline_client.payload = {
        "error": {"code": "synthetic-code", "displayMessage": "synthetic message"}
    }
    with pytest.raises(CasaApiError) as caught:
        await invoke(mail_api, case)
    assert (caught.value.code, caught.value.display_message) == (
        "synthetic-code",
        "synthetic message",
    )
    assert len(offline_client.calls) == 1


@pytest.mark.parametrize(
    "case", [case for case in CASES if case.body is None], ids=lambda case: case.name
)
async def test_bodyless_request_still_requires_basic_message_response(
    mail_api: TestApiMixin, offline_client: OfflineClient, case: WriteCase
) -> None:
    offline_client.status = 204
    offline_client.raw_body = ""
    with pytest.raises(CasaResponseError):
        await invoke(mail_api, case)
    assert offline_client.calls[0].body is None
    assert len(offline_client.calls) == 1


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (codecs.MailboxRecipientResponse, {"recipient": {"id": "synthetic"}}),
        (codecs.MailboxAutoArchiveResponse, {"success": 1}),
        (codecs.MailboxAutoArchiveResponse, {"success": False, "mailbox_auto_archive_days": True}),
        (codecs.UpdatePackageAutoArchiveResponse, {"success": "false"}),
        (
            codecs.UpdatePackageAutoArchiveResponse,
            {"success": True, "package_auto_archive_days": "7"},
        ),
        (codecs.TrackingNumberValidationResponse, {"tracking_number": "synthetic", "valid": True}),
        (
            codecs.TrackingNumberValidationResponse,
            {"tracking_number": 123, "valid": True, "carrier_matches": []},
        ),
        (
            codecs.TrackingNumberValidationResponse,
            {"tracking_number": "synthetic", "valid": 1, "carrier_matches": []},
        ),
        (
            codecs.TrackingNumberValidationResponse,
            {"tracking_number": "synthetic", "valid": True, "carrier_matches": [1]},
        ),
        (
            codecs.TrackingNumberValidationResponse,
            {"tracking_number": "synthetic", "valid": True, "carrier_matches": "carrier"},
        ),
        (codecs.CreateEntityResponse, {"entity_id": "synthetic"}),
        (codecs.CreateEntityResponse, {"entity_id": True, "message": "ok"}),
        (codecs.CreateLightingResponse, {"fixture_entity_id": "synthetic"}),
        (codecs.CreateLightingResponse, {"fixture_entity_id": "synthetic", "message": None}),
        (codecs.CreatePaintFromLibraryResponse, {}),
        (codecs.CreatePaintFromLibraryResponse, {"entity_id": 17}),
    ],
)
def test_strict_receipt_fields(model: type[BaseModel], data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_required_and_nullable_fields() -> None:
    required: list[tuple[type[BaseModel], str]] = [
        (codecs.MailboxAutoArchiveRequest, "mailbox_auto_archive_days"),
        (codecs.UpdatePackageAutoArchiveRequest, "package_auto_archive_days"),
        (codecs.AddPackageRequest, "tracking_number"),
        (codecs.AddPackageRequest, "name"),
        (codecs.AddPackageRequest, "direction"),
        (codecs.CreatePackagePickupItemRequest, "package_image_path"),
        (codecs.CreateLightingRequest, "fixture"),
        (codecs.CreateLightingRequest, "bulb"),
        (codecs.CreatePaintFromLibraryRequest, "paint_color_id"),
        (codecs.CreatePaintFromLibraryRequest, "room_ids"),
        (codecs.MailboxRecipientResponse, "recipient"),
        (codecs.MailboxAutoArchiveResponse, "success"),
        (codecs.TrackingNumberValidationResponse, "carrier_matches"),
        (codecs.CreateEntityResponse, "message"),
        (codecs.CreateLightingResponse, "message"),
        (codecs.CreatePaintFromLibraryResponse, "entity_id"),
    ]
    for model, key in required:
        assert model.model_fields[key].is_required()
    assert codecs.MailboxAutoArchiveResponse(success=True).mailbox_auto_archive_days is None
    assert codecs.UpdatePackageAutoArchiveResponse(success=False).package_auto_archive_days is None
    lighting = codecs.CreateLightingResponse(fixture_entity_id="synthetic", message="")
    assert lighting.bulb_entity_id is None
