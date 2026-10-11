"""High-level Casa API.

Confidence per method:

- VERIFIED: path and method confirmed against real traffic or a live call.
  Each docstring states how much of the body is confirmed: the envelope (top
  level keys) and, when the account returned data, the item shape inside lists.
- UNVERIFIED: provisional path and response schema from the app binary. HTTP
  method confidence can be LIKELY from static accessor evidence. Query inputs
  and decoder linkage can remain unknown. Server acceptance isn't established.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import aclosing, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from casahome._common import (
    _home,
    _member_home,
    _parse,
    _positive_int,
    _safe_home,
    _safe_id,
    is_unverified,
    unverified,
)
from casahome.client import CasaClient
from casahome.const import (
    APP_MARKETING_VERSION,
    CASA_APP_BUILD,
    CASA_APP_VERSION,
    CASA_DEVICE_APP,
    MAX_APP_BUILD,
)
from casahome.models import (
    BasicMessageResponse,
    Bootstrap,
    CreateTodoResponse,
    HomeBadgeCounts,
    HomeDetailsResponse,
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    MemberCredits,
    PackagesResponse,
    RequestDetails,
    RequestsResponse,
    SendRequestMessageRequest,
    SendRequestMessageResponse,
    TodoDetail,
    UpdateEntityPropertiesRequest,
    UserDeviceRequest,
    VisitsCalendarResponse,
    WeatherResponse,
)
from casahome.models.ai import CasaAIBootstrapResponse, CasaAIMessagesResponse
from casahome.models.assets import (
    HomeMembersResponse,
    ReleaseNotesResponse,
    UtilitiesInsightsResponse,
    VehiclesResponse,
)
from casahome.models.availability import MemberAvailabilityDetail
from casahome.models.catalogs import (
    InventoryEnumsResponse,
    InventoryMakesResponse,
    RecurringVendor,
    RecurringVendorCategoriesResponse,
    RecurringVendorCategory,
    RecurringVendorsResponse,
    RoomType,
    RoomTypesResponse,
)
from casahome.models.documents import (
    DocumentDetailsResponse,
    DocumentsResponse,
    DocumentStructureSuggestionsResponse,
    DocumentSuggestionsResponse,
    DocumentThumbnailResponse,
    DocumentTypesResponse,
    WorkDocumentSourceResponse,
)
from casahome.models.feed import HomeFeedResponse
from casahome.models.help_center import HelpCenterBundleResponse
from casahome.models.home import SimpleEntity
from casahome.models.images import (
    MatterportImage,
    MatterportImagesResponse,
    RoomImageOptionsResponse,
)
from casahome.models.maintenance import (
    AutopilotCategoriesResponse,
    AutopilotCategory,
    CalendarBusyResponse,
    CompletedRequestsResponse,
    InventoryServiceHistoryResponse,
)
from casahome.models.membership import MembershipDetails, MembershipSavings
from casahome.models.paint import (
    InventoryPaintMatchesResponse,
    PaintBrandsResponse,
    PaintCollectionsResponse,
    PaintColorsResponse,
    PaintSearchResponse,
)
from casahome.models.preferences import (
    AccessPreferencesResponse,
    CalendarSyncResponse,
    NotificationSettingsResponse,
    OnboardingAvailabilityResponse,
    OnboardingDetailsResponse,
    SchedulePreferencesResponse,
)
from casahome.models.purchases import PurchasesResponse, ScopedPurchasesResponse
from casahome.models.read_todos import SuggestedTodosResponse, TodoDetailsResponse
from casahome.models.referral import ReferralCodeResponse
from casahome.models.tasks import BookableHandymanTasksResponse, GroupedTaskDetails, TaskDetails
from casahome.models.taxes import PropertyTaxesResponse
from casahome.models.todos import CreateTodoBody
from casahome.models.visits import VendorVisitDetails, VisitCallsResponse, VisitConversation
from casahome.models.write_contracts import CreateTodoBody as StrictCreateTodoBody
from casahome.models.write_contracts import _write_payload
from casahome.streaming import CasaAIEvent, _stream_events, _validate_cursor, unverified_stream
from casahome.writes import VerifiedWritesMixin

__all__ = ["CasaApi", "is_unverified", "unverified"]


def _local_iana_timezone() -> str:
    """Best-effort IANA zone name (Casa rejects abbreviations like ``PDT``)."""
    env = os.environ.get("TZ", "").lstrip(":")
    if "/" in env:
        return env
    try:
        target = str(Path("/etc/localtime").resolve())
    except OSError:
        return "UTC"
    marker = "zoneinfo/"
    return target.split(marker, 1)[1] if marker in target else "UTC"


def _epoch(value: datetime | int) -> int:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("calendar bounds must be timezone-aware datetimes")
        return int(value.timestamp())
    return int(value)


def _app_build(value: int, name: str) -> str:
    """Validate a build number the app would send as a positive Int32."""
    text = _positive_int(value, name)
    if value > MAX_APP_BUILD:
        raise ValueError(f"{name} must fit in a 32-bit signed integer")
    return text


def _busy_bounds(start: datetime | int, end: datetime | int) -> dict[str, str]:
    for value in (start, end):
        if isinstance(value, datetime):
            if value.utcoffset() is None:
                raise ValueError("calendar bounds must be timezone-aware datetimes")
        elif isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("calendar bounds must be aware datetimes or integer epoch seconds")
    start_epoch, end_epoch = _epoch(start), _epoch(end)
    if end_epoch <= start_epoch:
        raise ValueError("end must be after start")
    return {"start_time": str(start_epoch), "end_time": str(end_epoch)}


class CasaApi(VerifiedWritesMixin):
    """Typed wrappers around Casa member endpoints.

    Live-verified writes come from ``VerifiedWritesMixin`` (``casahome.writes``).
    Writes execute only when callers explicitly await them and make exactly
    one attempt: the client force-refreshes the ID token first and raises
    ``CasaAuthError`` on HTTP 401 instead of retrying.
    """

    def __init__(
        self,
        client: CasaClient,
        *,
        device_id: str | None = None,
        timezone: str | None = None,
    ) -> None:
        """``device_id`` should be persisted and reused by long-lived callers.

        ``bootstrap`` registers the device with Casa, so a fresh random id on
        every start piles up phantom devices on the account. ``timezone`` must
        be an IANA name; it's detected from the OS when omitted.
        """
        self.client = client
        self.device_id = device_id or str(uuid.uuid4()).upper()
        self._timezone = timezone

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        refresh_token: str,
        *,
        device_id: str | None = None,
        timezone: str | None = None,
    ) -> AsyncIterator[CasaApi]:
        """One-liner for scripts: owns its session, closes it on exit."""
        async with CasaClient.create(refresh_token) as client:
            yield cls(client, device_id=device_id, timezone=timezone)

    def default_device(self) -> UserDeviceRequest:
        """Device descriptor sent with ``bootstrap`` when none is supplied."""
        return UserDeviceRequest(
            device_id=self.device_id,
            device_name="iPhone",
            system_name="iOS",
            system_version="27.0",
            model="iPhone",
            language="en-US",
            timezone=self._timezone or _local_iana_timezone(),
            app=CASA_DEVICE_APP,
            app_version=APP_MARKETING_VERSION,
            app_build=CASA_APP_VERSION,
            fcm_token="",
            voip_token="",
        )

    # VERIFIED ---------------------------------------------------------------

    async def bootstrap(self, device: UserDeviceRequest | None = None) -> Bootstrap:
        """VERIFIED. User profile, homes, badge counts, app update info.

        Bootstrap is a POST, but it keeps the one-shot 401 retry on purpose.
        It registers this ``device_id`` with Casa, and repeating it with the
        same descriptor re-registers the same device rather than creating new
        state. It's the session-start call, so a stale cached token is likely.
        Real writes never retry on 401.
        """
        device = device or self.default_device()
        data = await self.client.post(
            "/protected/member/bootstrap",
            json={"user_device": device.model_dump(mode="json")},
            retry_on_401=True,
        )
        return _parse(Bootstrap, data)

    async def onboarding_details(self, home_id: str) -> dict[str, Any] | None:
        """VERIFIED GET and populated calendar_events envelope.

        Returns raw data for backward compatibility, or None on a bodyless 304.
        Use onboarding_details_typed for validated event metadata.
        """
        data = await self.client.get(f"/protected/home/{home_id}/onboarding/details")
        return data if isinstance(data, dict) else None

    # VERIFIED reads ---------------------------------------------------------
    #
    # Each method below returned HTTP 200 in live traffic and parsed with the
    # model shown. "Envelope" means the top-level keys. "Item shape" means the
    # elements inside lists, which are only confirmed when a response had some.

    async def home_details(self, home_id: str) -> HomeDetailsResponse:
        """VERIFIED (live GET, 2026-10). Stories, rooms, and inventory entities.

        Path, method, envelope, and entity item shape verified against a populated
        response.
        """
        data = await self.client.get(f"{_member_home(home_id)}/inventory/v3")
        return _parse(HomeDetailsResponse, data)

    async def badge_counts(self, home_id: str) -> HomeBadgeCounts:
        """VERIFIED (live GET, 2026-10). Cheap poll for unread counts per feature.

        Path, method, and full shape verified: ``computed_at``, ``total``, and
        ``features`` keyed by feature name.
        """
        data = await self.client.get(f"{_home(home_id)}/badge_counts")
        return _parse(HomeBadgeCounts, data)

    async def weather(self, home_id: str) -> WeatherResponse:
        """VERIFIED (live GET, 2026-10). Current conditions at the home.

        Path, method, and full shape verified. ``temperature_units`` observed as ``"F"``.
        """
        data = await self.client.get(f"{_home(home_id)}/weather")
        return _parse(WeatherResponse, data)

    async def requests_tab(self, home_id: str) -> RequestsResponse:
        """VERIFIED path, method, envelope and request card shape (live GET, 2026-10).

        Requests, tasks, and to-dos lanes in one call. Request cards were seen
        populated with id, title, latest_message_preview, emoji, updated_at,
        has_unread_messages, the pending_* and ready_to_review_availability
        counts, concierge_awaiting_reply, type (``concierge``) and vendor_visits.
        Task card items remain UNVERIFIED.
        """
        data = await self.client.get(f"{_home(home_id)}/requests_tab")
        return _parse(RequestsResponse, data)

    async def calendar(
        self, home_id: str, start: datetime | int, end: datetime | int
    ) -> VisitsCalendarResponse:
        """VERIFIED path, method, query keys, and envelope (live GET, 2026-10).

        The server accepted ``start_time`` and ``end_time`` as stringified epoch
        seconds and returned ``{"events": []}``. With no events returned, the
        event item shape and the server's interpretation of the bounds (units,
        inclusivity) remain UNVERIFIED.

        Accepts aware datetimes or epoch seconds. Naive datetimes are rejected,
        since guessing a zone silently shifts the window.
        """
        data = await self.client.get(
            f"{_home(home_id)}/calendar",
            params={"start_time": str(_epoch(start)), "end_time": str(_epoch(end))},
        )
        return _parse(VisitsCalendarResponse, data)

    async def credits_summary(self, home_id: str) -> MemberCredits:
        """VERIFIED (live GET, 2026-10). Credit balance and handyman rate.

        Path, method, and full shape verified: ``home_id``, ``total_available``,
        ``handyman_hourly_rate_cents``.
        """
        data = await self.client.get(f"{_home(home_id)}/credits/summary")
        return _parse(MemberCredits, data)

    async def mailbox(self, home_id: str) -> MailboxOverviewResponse:
        """VERIFIED path, method, and envelope (live GET, 2026-10).

        Observed ``{"mailbox": null}``, so the populated mailbox shape is UNVERIFIED.
        """
        data = await self.client.get(f"{_home(home_id)}/mailbox")
        return _parse(MailboxOverviewResponse, data)

    async def mail_items(self, home_id: str) -> MailboxMailItemsResponse:
        """VERIFIED path, method, and envelope (live GET, 2026-10).

        The list was empty, so the mail item shape is UNVERIFIED.
        """
        data = await self.client.get(f"{_home(home_id)}/mailbox/mail_items")
        return _parse(MailboxMailItemsResponse, data)

    async def packages(self, home_id: str) -> PackagesResponse:
        """VERIFIED path, method, and envelope (live GET, 2026-10).

        No packages were returned, so the package item shape is UNVERIFIED.
        """
        data = await self.client.get(f"{_home(home_id)}/packages/v3")
        return _parse(PackagesResponse, data)

    # Further VERIFIED reads (live GET, 2026-10).

    async def completed_requests(
        self, home_id: str, page: int, page_size: int = 100, search: str | None = None
    ) -> CompletedRequestsResponse:
        """VERIFIED (live GET, 2026-10).

        kind=requests, page=1, page_size=100 and the pagination envelope observed.
        RequestCard items were empty. Search and other pages remain UNVERIFIED.
        Blank search is omitted. Nonempty search is trimmed.
        """
        path = f"{_safe_home(home_id)}/requests_tab/completed"
        params = {
            "kind": "requests",
            "page": _positive_int(page, "page"),
            "page_size": _positive_int(page_size, "page_size"),
        }
        if search is not None and (trimmed := search.strip()):
            params["search"] = trimmed
        return _parse(CompletedRequestsResponse, await self.client.get(path, params=params))

    async def autopilot_plans(
        self,
        home_id: str,
        requirement_kinds: Sequence[Literal["entity_property", "room_property"]] = (
            "entity_property",
            "room_property",
        ),
    ) -> list[AutopilotCategory]:
        """VERIFIED (live GET, 2026-10).

        Bare category list with populated plans, requirements, associations,
        pricing policies and ineligible plans. Both default requirement kinds
        observed together. Subset filtering semantics remain UNVERIFIED.
        """
        path = f"{_safe_home(home_id)}/autopilot/list/v2"
        if (
            isinstance(requirement_kinds, str)
            or not requirement_kinds
            or any(kind not in {"entity_property", "room_property"} for kind in requirement_kinds)
        ):
            raise ValueError("requirement_kinds must contain entity_property or room_property")
        data = await self.client.get(
            path, params={"requirement_kinds": ",".join(requirement_kinds)}
        )
        return _parse(AutopilotCategoriesResponse, data).root

    async def inventory_service_history(
        self, home_id: str, target_type: Literal["entity", "room", "home"], target_id: str
    ) -> InventoryServiceHistoryResponse:
        """VERIFIED (live GET, 2026-10) for room and home targets.

        Empty plans/history_items envelopes observed. Entity target and populated
        item schemas remain UNVERIFIED.
        """
        path = f"{_safe_home(home_id)}/inventory/service_history"
        if target_type not in {"entity", "room", "home"}:
            raise ValueError("target_type must be entity, room, or home")
        data = await self.client.get(
            path,
            params={
                "inventory_target_type": target_type,
                "inventory_target_id": _safe_id(target_id),
            },
        )
        return _parse(InventoryServiceHistoryResponse, data)

    async def calendar_busy(
        self,
        home_id: str,
        start: datetime | int,
        end: datetime | int,
        *,
        google_calendar_ids: Sequence[str] | None = None,
    ) -> CalendarBusyResponse:
        """VERIFIED (live GET, 2026-10).

        Epoch query keys, blocks=[] and google_status observed. Block items,
        bounds interpretation and google_calendar_ids filtering UNVERIFIED.
        Optional Google IDs are comma-joined query values, not path segments.
        """
        path = f"{_safe_home(home_id)}/calendar_busy"
        params = _busy_bounds(start, end)
        if google_calendar_ids is not None:
            if (
                isinstance(google_calendar_ids, str)
                or not google_calendar_ids
                or any(
                    not isinstance(value, str)
                    or not value.strip()
                    or "," in value
                    or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)
                    for value in google_calendar_ids
                )
            ):
                raise ValueError("google_calendar_ids must contain nonempty IDs without commas")
            params["google_calendar_ids"] = ",".join(google_calendar_ids)
        return _parse(CalendarBusyResponse, await self.client.get(path, params=params))

    async def room_image_options(self, home_id: str, room_id: str) -> RoomImageOptionsResponse:
        """VERIFIED (live GET, 2026-10).

        Populated matterport_images. member_image was null, its shape UNVERIFIED.
        Returns metadata only, never follows the image URLs.
        """
        path = f"{_safe_home(home_id, member=True)}/room/{_safe_id(room_id)}/image/options"
        return _parse(RoomImageOptionsResponse, await self.client.get(path))

    async def room_image_candidates(self, home_id: str) -> RoomImageOptionsResponse:
        """VERIFIED (live GET, 2026-10).

        Populated matterport_images, null member_image. Home-wide route, no room ID.
        Member image shape remains UNVERIFIED. Metadata only.
        """
        path = f"{_safe_home(home_id, member=True)}/room_image_candidates"
        return _parse(RoomImageOptionsResponse, await self.client.get(path))

    async def paint_search(self, home_id: str, q: str) -> PaintSearchResponse:
        """VERIFIED (live GET, 2026-10). Populated results for a query."""
        path = f"{_safe_home(home_id)}/paint/library/search"
        return _parse(PaintSearchResponse, await self.client.get(path, params={"q": q}))

    async def paint_brands(self, home_id: str) -> PaintBrandsResponse:
        """VERIFIED (live GET, 2026-10). Populated brands."""
        return _parse(
            PaintBrandsResponse,
            await self.client.get(f"{_safe_home(home_id)}/paint/library/brands"),
        )

    async def paint_collections(
        self, home_id: str, brand_id: int | str
    ) -> PaintCollectionsResponse:
        """VERIFIED (live GET, 2026-10). Populated collections.

        Accepts integer or string catalog IDs unchanged. No UUID coercion.
        """
        path = f"{_safe_home(home_id)}/paint/library/brands/{_safe_id(brand_id)}/collections"
        return _parse(PaintCollectionsResponse, await self.client.get(path))

    async def paint_colors(self, home_id: str, collection_id: int | str) -> PaintColorsResponse:
        """VERIFIED (live GET, 2026-10). Populated color rows."""
        path = f"{_safe_home(home_id)}/paint/library/collections/{_safe_id(collection_id)}/colors"
        return _parse(PaintColorsResponse, await self.client.get(path))

    async def todo_details(self, home_id: str, todo_id: str) -> TodoDetailsResponse:
        """VERIFIED (live GET, 2026-10). Populated todo, attachments, question rounds.

        Question rounds (id, sequence, state, questions) and a ``request``
        destination were observed. Individual question items stay JSON.
        """
        path = f"{_safe_home(home_id)}/todos/{_safe_id(todo_id)}"
        return _parse(TodoDetailsResponse, await self.client.get(path))

    async def suggested_todos(self, home_id: str) -> SuggestedTodosResponse:
        """VERIFIED (live GET, 2026-10). Populated suggested_todos.

        Core fields and attachments observed, not question rounds or destination.
        This call doesn't create or accept suggestions.
        """
        return _parse(
            SuggestedTodosResponse, await self.client.get(f"{_safe_home(home_id)}/suggested_todos")
        )

    async def work_document_source(
        self,
        home_id: str,
        *,
        todo_id: str | None = None,
        task_id: str | None = None,
        request_id: str | None = None,
    ) -> WorkDocumentSourceResponse:
        """VERIFIED (live GET, 2026-10) for todo_id with source=null.

        Exactly one selector required.
        task_id/request_id and populated source schemas remain UNVERIFIED.
        """
        path = f"{_safe_home(home_id)}/work_document_source"
        selectors = {
            key: _safe_id(value)
            for key, value in {
                "todo_id": todo_id,
                "task_id": task_id,
                "request_id": request_id,
            }.items()
            if value is not None
        }
        if len(selectors) != 1:
            raise ValueError("provide exactly one of todo_id, task_id, request_id")
        return _parse(WorkDocumentSourceResponse, await self.client.get(path, params=selectors))

    async def inventory_item(self, home_id: str, entity_id: str) -> SimpleEntity:
        """VERIFIED (live GET, 2026-10). Populated bare SimpleEntity.

        Reuses the inventory/v3 entity model and preserves extras.
        """
        path = f"{_safe_home(home_id, member=True)}/entity/{_safe_id(entity_id)}/v2"
        return _parse(SimpleEntity, await self.client.get(path))

    async def documents(
        self,
        home_id: str,
        *,
        cursor: str | None = None,
        limit: int = 30,
        q: str | None = None,
        document_type: str | None = None,
        sort: str | None = None,
    ) -> DocumentsResponse:
        """VERIFIED (live GET, 2026-10). Populated documents with limit and sort.

        The app sent ``limit=30&sort=uploaded`` and got ``documents`` items plus
        ``next_cursor``. ``sort`` defaults to unset for compatibility. Pass
        ``sort="uploaded"`` to match the app. ``q``, ``document_type`` and
        ``cursor`` behavior remain UNVERIFIED. Only non-None filters are sent.
        Cursors remain opaque query strings.
        """
        path = f"{_safe_home(home_id)}/documents"
        params = {"limit": _positive_int(limit, "limit")}
        params.update(
            {
                key: value
                for key, value in {
                    "cursor": cursor,
                    "q": q,
                    "document_type": document_type,
                    "sort": sort,
                }.items()
                if value is not None
            }
        )
        return _parse(DocumentsResponse, await self.client.get(path, params=params))

    async def document_types(self, home_id: str) -> DocumentTypesResponse:
        """VERIFIED (live GET, 2026-10). Populated types and limits."""
        return _parse(
            DocumentTypesResponse, await self.client.get(f"{_safe_home(home_id)}/documents/types")
        )

    async def casa_ai_bootstrap(self, home_id: str) -> CasaAIBootstrapResponse:
        """VERIFIED (live GET, 2026-10). Conversation and starter suggestions.

        Messages empty, active_response
        null. Populated message/active-response schemas UNVERIFIED. No send or SSE.
        """
        return _parse(
            CasaAIBootstrapResponse, await self.client.get(f"{_safe_home(home_id)}/casa_ai")
        )

    async def casa_ai_messages(
        self,
        home_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
    ) -> CasaAIMessagesResponse:
        """VERIFIED (live GET, 2026-10). Parameter-free, empty items envelope.

        Optional limit/before behavior
        and populated message schemas UNVERIFIED. Default sends no query keys.
        """
        path = f"{_safe_home(home_id)}/casa_ai/messages"
        params: dict[str, str] = {}
        if limit is not None:
            params["limit"] = _positive_int(limit, "limit")
        if before is not None:
            params["before"] = before
        return _parse(CasaAIMessagesResponse, await self.client.get(path, params=params))

    async def schedule_preferences(self, home_id: str) -> SchedulePreferencesResponse:
        """VERIFIED (live GET, 2026-10). Populated days and windows."""
        return _parse(
            SchedulePreferencesResponse,
            await self.client.get(f"{_safe_home(home_id)}/schedule_preferences"),
        )

    async def notification_settings(self, home_id: str) -> NotificationSettingsResponse:
        """VERIFIED (live GET, 2026-10). Populated groups, types and channels."""
        return _parse(
            NotificationSettingsResponse,
            await self.client.get(f"{_safe_home(home_id)}/notification_settings"),
        )

    async def onboarding_availability(self, home_id: str) -> OnboardingAvailabilityResponse:
        """VERIFIED (live GET, 2026-10). Populated slots and timezone."""
        return _parse(
            OnboardingAvailabilityResponse,
            await self.client.get(f"{_safe_home(home_id)}/onboarding/availability"),
        )

    async def onboarding_details_typed(self, home_id: str) -> OnboardingDetailsResponse | None:
        """VERIFIED (live GET, 2026-10). Populated calendar_events.

        Typed companion to the backward-compatible raw onboarding_details.
        A bodyless 304 still returns None. Invalid nonempty bodies raise CasaResponseError.
        """
        data = await self.client.get(f"{_safe_home(home_id)}/onboarding/details")
        return None if data is None else _parse(OnboardingDetailsResponse, data)

    async def vehicles(self, home_id: str) -> VehiclesResponse:
        """VERIFIED (live GET, 2026-10). Envelope only, vehicles=[].

        Populated vehicles UNVERIFIED. Static optional fields, opaque readings.
        """
        return _parse(VehiclesResponse, await self.client.get(f"{_safe_home(home_id)}/vehicles"))

    async def utilities_insights(self, home_id: str) -> UtilitiesInsightsResponse:
        """VERIFIED (live GET, 2026-10). Envelope only, services=[].

        Populated service, statement, graph and account schemas remain UNVERIFIED.
        """
        return _parse(
            UtilitiesInsightsResponse,
            await self.client.get(f"{_safe_home(home_id)}/utilities/insights"),
        )

    async def room_types(self) -> list[RoomType]:
        """VERIFIED (live GET, 2026-10). Populated bare list."""
        return _parse(
            RoomTypesResponse, await self.client.get("/protected/inventory/room_types/list")
        ).root

    async def home_members(self, home_id: str) -> HomeMembersResponse:
        """VERIFIED (live GET, 2026-10). Populated members envelope."""
        return _parse(
            HomeMembersResponse, await self.client.get(f"{_safe_home(home_id)}/home_members/list")
        )

    async def purchases(self, home_id: str) -> PurchasesResponse:
        """VERIFIED (live GET, 2026-10). Empty item lists plus context metadata.

        Item schemas UNVERIFIED. No
        approval, payment or return mutation. Non-purchase invoices weren't populated.
        """
        return _parse(PurchasesResponse, await self.client.get(f"{_safe_home(home_id)}/purchases"))

    async def property_taxes(self, home_id: str) -> PropertyTaxesResponse:
        """VERIFIED (live GET, 2026-10). Refresh metadata and reports=[].

        Report/assessment/installment item schemas remain UNVERIFIED.
        """
        return _parse(
            PropertyTaxesResponse, await self.client.get(f"{_safe_home(home_id)}/property_taxes")
        )

    async def matterport_images(self, home_id: str) -> list[MatterportImage]:
        """VERIFIED (live GET, 2026-10). Populated bare image list.

        Photo metadata only. No downstream URL fetch.
        """
        return _parse(
            MatterportImagesResponse,
            await self.client.get(f"{_safe_home(home_id)}/matterport/images"),
        ).root

    async def release_notes(self) -> ReleaseNotesResponse:
        """VERIFIED (live GET, 2026-10). Populated data and sections for member_ios/all."""
        return _parse(
            ReleaseNotesResponse, await self.client.get("/protected/release_notes/member_ios/all")
        )

    async def access_preferences(self, home_id: str) -> AccessPreferencesResponse:
        """VERIFIED (live GET, 2026-10). home_id and nullable metadata."""
        return _parse(
            AccessPreferencesResponse,
            await self.client.get(f"{_safe_home(home_id)}/access_preferences"),
        )

    async def calendar_sync(self, home_id: str) -> CalendarSyncResponse:
        """VERIFIED (live GET, 2026-10). Metadata with empty calendars.

        Calendar items and sync_progress remain UNVERIFIED. Reads only, no OAuth action.
        """
        return _parse(
            CalendarSyncResponse, await self.client.get(f"{_safe_home(home_id)}/calendar_sync")
        )

    async def inventory_makes(self, entity_type_id: str) -> InventoryMakesResponse:
        """VERIFIED (live GET, 2026-10). Populated makes catalog."""
        path = f"/protected/member/inventory/makes/entity_type/{_safe_id(entity_type_id)}"
        return _parse(InventoryMakesResponse, await self.client.get(path))

    async def recurring_vendor_categories(self, home_id: str) -> list[RecurringVendorCategory]:
        """VERIFIED (live GET, 2026-10). Populated bare category list."""
        return _parse(
            RecurringVendorCategoriesResponse,
            await self.client.get(f"{_safe_home(home_id)}/dtd/categories"),
        ).root

    async def recurring_vendors(self, home_id: str) -> list[RecurringVendor]:
        """VERIFIED (live GET, 2026-10). Empty bare list.

        Populated recurring vendor fields UNVERIFIED, nested events/invoices opaque.
        """
        return _parse(
            RecurringVendorsResponse, await self.client.get(f"{_safe_home(home_id)}/dtd/list")
        ).root

    async def bookable_handyman_tasks(
        self, home_id: str, *, include_current_vendor_visit_id: str | None = None
    ) -> BookableHandymanTasksResponse:
        """VERIFIED (live GET, 2026-10). Parameter-free, items/availability envelope.

        Items were empty. Populated items remain JsonValue because their wire
        tags aren't known. The optional query key is inferred from the app only.
        Its value encoding and behavior remain UNVERIFIED. No booking/options call.
        """
        path = f"{_safe_home(home_id)}/vendor_visits/handyman/bookable_tasks"
        params = (
            {"include_current_vendor_visit_id": _safe_id(include_current_vendor_visit_id)}
            if include_current_vendor_visit_id is not None
            else {}
        )
        return _parse(BookableHandymanTasksResponse, await self.client.get(path, params=params))

    async def inventory_enums(self, enum_type: str) -> InventoryEnumsResponse:
        """VERIFIED (live GET, 2026-10). Populated enums.

        ``enum_type`` is a property's string ``enum_type`` key, such as
        ``light_fixture_type`` or ``home_type``. It isn't a UUID, an entity-type
        ID or a make ID. Observed options parsed as ``InventoryEnumOption``.
        Other keys and empty catalogs are UNVERIFIED.
        """
        path = f"/protected/member/inventory/enums/enum_type/{_safe_id(enum_type)}"
        return _parse(InventoryEnumsResponse, await self.client.get(path))

    async def inventory_paint_matches(
        self, home_id: str, entity_id: str
    ) -> InventoryPaintMatchesResponse:
        """VERIFIED (live GET, 2026-10). Populated matches.

        Uses the non-member home base with a paint entity ID. The envelope was
        ``matches`` (each parsed as ``InventoryPaintMatch``) plus a
        Boolean ``is_manually_added``. Integer catalog IDs. Reads matches only,
        never applies one. Non-paint entities and empty results are UNVERIFIED.
        """
        path = f"{_safe_home(home_id)}/entity/{_safe_id(entity_id)}/paint/library/match"
        return _parse(InventoryPaintMatchesResponse, await self.client.get(path))

    async def help_center_bundle(self, app_id: str) -> HelpCenterBundleResponse:
        """VERIFIED (live GET, 2026-10) for ``app_id="member_ios"``.

        Envelope ``data`` with ``app``, ``topics`` and ``articles``, all parsed
        as the existing models. Those models accept both camelCase aliases and
        snake_case names, so the wire key spelling isn't pinned.
        Other app IDs are UNVERIFIED. No article-view tracking or feedback POST.
        """
        path = f"/protected/help_center/{_safe_id(app_id)}/bundle"
        return _parse(HelpCenterBundleResponse, await self.client.get(path))

    async def referral_code(self) -> ReferralCodeResponse:
        """VERIFIED (live GET, 2026-10). Envelope only.

        ``referral_code`` held ``code``, ``referral_url``, a ``display`` object
        and a ``referred_homes`` list. Display keys and referred-home item
        shapes are UNVERIFIED and stay ``JsonValue``. The SDK never fetches the URL.
        """
        data = await self.client.get("/protected/member/referral_code/v2")
        return _parse(ReferralCodeResponse, data)

    async def home_feed(self, home_id: str, *, app_build: int = CASA_APP_BUILD) -> HomeFeedResponse:
        """VERIFIED (live GET, 2026-10) with ``app_build=698``.

        Envelope ``cards`` with populated cards, each with ``id``,
        ``template_id``, ``name``, a template-specific ``props`` dict, integer
        show-window offsets and an empty ``children`` list. Omitting
        ``app_build`` got HTTP 400 ``INVALID_INPUT_PARAMETERS``, so it's always
        sent. The app sends its CFBundleVersion as an Int32. Props stay
        ``JsonValue``, and nested children shapes are UNVERIFIED. The SDK never
        follows image or action URLs found in props.
        """
        path = f"{_safe_home(home_id)}/feed"
        params = {"app_build": _app_build(app_build, "app_build")}
        return _parse(HomeFeedResponse, await self.client.get(path, params=params))

    async def release_notes_diff(
        self, *, current_build: int = CASA_APP_BUILD
    ) -> ReleaseNotesResponse:
        """VERIFIED (live GET, 2026-10) with ``currentBuild=698``.

        Notes newer than ``current_build``. The camelCase ``currentBuild`` key
        comes from the app, and the bare route got HTTP 400, so it's always
        sent. Same ``data`` envelope as ``release_notes``: populated notes with
        integer ``date`` and ``min_build_number``, nullable ``max_build_number``
        and sections. Doesn't record a highest-seen build.
        """
        params = {"currentBuild": _app_build(current_build, "current_build")}
        data = await self.client.get("/protected/release_notes/member_ios/diff", params=params)
        return _parse(ReleaseNotesResponse, data)

    # UNVERIFIED reads -------------------------------------------------------

    async def membership_info(self, home_id: str) -> MembershipDetails:
        """VERIFIED (live GET, 2026-10) envelope for an active membership.

        HTTP 200 bare object with amount, amount_cents, benefits,
        cancel_at_period_end, current_period_start/end, interval, member_since,
        name, next_billing_date, status and Stripe customer/subscription IDs.
        An earlier probe on a home without an active membership returned 404,
        so expect ``CasaApiError`` 404 in that state.

        No billing-detail, lifecycle or payment calls. Amount and interval stay raw.
        """
        path = f"{_safe_home(home_id)}/membership/info"
        return _parse(MembershipDetails, await self.client.get(path))

    @unverified
    async def membership_savings(self, home_id: str) -> MembershipSavings:
        """Membership savings totals and breakdown.

        A live GET (2026-10) returned 404 ``MEMBERSHIP_SAVINGS_NOT_FOUND``, even
        for an active membership. The domain-specific code suggests a routed
        handler with no data, not proof of the schema.

        Provisional bare object. Explicit seconds/cents retained. No inferred
        reporting period, date parsing, currency conversion or financial actions.
        """
        path = f"{_safe_home(home_id)}/membership_savings"
        return _parse(MembershipSavings, await self.client.get(path))

    @unverified
    async def availability_request_details(
        self, home_id: str, availability_request_id: str
    ) -> MemberAvailabilityDetail:
        """One availability request with its slots and constraints.

        Availability metadata and slots only. No selection or submission.
        """
        path = f"{_safe_home(home_id)}/availability_requests/{_safe_id(availability_request_id)}"
        return _parse(MemberAvailabilityDetail, await self.client.get(path))

    async def document_details(self, home_id: str, document_id: str) -> DocumentDetailsResponse:
        """VERIFIED (live GET, 2026-10). ``{"document": {...}}`` populated.

        Metadata plus organization and extraction status. No download.
        """
        path = f"{_safe_home(home_id)}/documents/{_safe_id(document_id)}"
        return _parse(DocumentDetailsResponse, await self.client.get(path))

    async def document_thumbnail(self, home_id: str, document_id: str) -> DocumentThumbnailResponse:
        """VERIFIED (live GET, 2026-10). Signed preview URLs for one document.

        Observed ``url``, ``expires_at`` (epoch seconds), ``preview_pages`` and
        ``page_count_url``. The URLs are short-lived signed credentials. The
        library never fetches them. Don't log them.
        """
        path = f"{_safe_home(home_id)}/documents/{_safe_id(document_id)}/thumbnail"
        return _parse(DocumentThumbnailResponse, await self.client.get(path))

    @unverified
    async def document_suggestions(
        self, home_id: str, document_id: str
    ) -> DocumentSuggestionsResponse:
        """Existing suggestions for one document.

        Reads existing suggestions, including sensitive text/citations. Doesn't
        analyze the document, create work, or accept/dismiss suggestions.
        """
        path = f"{_safe_home(home_id)}/documents/{_safe_id(document_id)}/suggestions"
        return _parse(DocumentSuggestionsResponse, await self.client.get(path))

    async def document_structure_suggestions(
        self, home_id: str, document_id: str
    ) -> DocumentStructureSuggestionsResponse:
        """VERIFIED (live GET, 2026-10) envelope, observed ``{"suggestions": []}``.

        Populated item fields are static and UNVERIFIED. Reads only, never
        responds or edits inventory.
        """
        path = f"{_safe_home(home_id)}/documents/{_safe_id(document_id)}/structure_suggestions"
        return _parse(DocumentStructureSuggestionsResponse, await self.client.get(path))

    async def request_purchases(self, home_id: str, request_id: str) -> ScopedPurchasesResponse:
        """VERIFIED (live GET, 2026-10) envelope for one request's purchases.

        Observed context_title, pending_purchase_approvals, approved_purchases,
        purchased_items and next_package_pickup_by (epoch seconds). No
        non_purchase_invoices key. Item shapes remain static.
        No approval, returns, invoice-detail or payment calls.
        """
        path = f"{_safe_home(home_id)}/requests/{_safe_id(request_id)}/purchases"
        return _parse(ScopedPurchasesResponse, await self.client.get(path))

    @unverified
    async def task_details(self, home_id: str, task_id: str) -> TaskDetails:
        """One task with its updates and attachments.

        Provisional bare object. Reads updates/attachments without fetching URLs.
        No scheduling, edit, delete or concierge-transfer action.
        """
        path = f"{_safe_home(home_id)}/tasks/{_safe_id(task_id)}"
        return _parse(TaskDetails, await self.client.get(path))

    @unverified
    async def vendor_visit_details(self, home_id: str, visit_id: str) -> VendorVisitDetails:
        """One vendor visit with request, vendors and previews.

        Provisional bare object. Task-item tags and feedback stay opaque JSON.
        The legacy VendorVisit model isn't changed. No visit mutation.
        """
        path = f"{_safe_home(home_id)}/vendor_visits/{_safe_id(visit_id)}"
        return _parse(VendorVisitDetails, await self.client.get(path))

    @unverified
    async def vendor_visit_autopilot_plan(
        self, home_id: str, visit_id: str, plan_id: str
    ) -> GroupedTaskDetails:
        """Grouped Autopilot tasks for one visit and plan.

        Provisional bare grouped tasks, not the home-wide Autopilot catalog model.
        """
        path = (
            f"{_safe_home(home_id)}/vendor_visits/{_safe_id(visit_id)}"
            f"/autopilot_plans/{_safe_id(plan_id)}"
        )
        return _parse(GroupedTaskDetails, await self.client.get(path))

    @unverified
    async def vendor_visit_calls(self, home_id: str, visit_id: str) -> VisitCallsResponse:
        """Call history metadata for one vendor visit.

        Call history metadata only, not VisitCallGrant. Never starts, answers,
        declines, ends or joins a call. Personal participants/times are returned.
        """
        path = f"{_safe_home(home_id)}/vendor_visits/{_safe_id(visit_id)}/calls"
        return _parse(VisitCallsResponse, await self.client.get(path))

    @unverified
    async def vendor_visit_conversation(self, home_id: str, visit_id: str) -> VisitConversation:
        """Conversation metadata and messages for one vendor visit.

        Returns sensitive messages and participant metadata. Part tags remain
        opaque JSON. No send, read-marking, call-control or vendor stream request.
        """
        path = f"{_safe_home(home_id)}/vendor_visits/{_safe_id(visit_id)}/conversation"
        return _parse(VisitConversation, await self.client.get(path))

    @unverified
    async def vendor_visit_purchases(self, home_id: str, visit_id: str) -> ScopedPurchasesResponse:
        """Purchases scoped to one vendor visit. Provisional response model.

        Same scoped envelope as request_purchases. No financial actions.
        """
        path = f"{_safe_home(home_id)}/vendor_visits/{_safe_id(visit_id)}/purchases"
        return _parse(ScopedPurchasesResponse, await self.client.get(path))

    @unverified_stream
    async def casa_ai_events(
        self, home_id: str, after: str | None = None
    ) -> AsyncGenerator[CasaAIEvent, None]:
        """Opt-in GET SSE stream. No send, bootstrap, or automatic reconnection.

        Calling this method opts into the stream contract inferred from the app.
        A live connection returned HTTP 200, text/event-stream, and stream.hello.
        Other event contracts are inferred and covered by synthetic tests only.
        Resume forwards the same opaque cursor as after and Last-Event-ID.
        thread.update payloads are JsonValue, with no guessed change variants.
        resync_required closes the response, yields a typed signal, and finishes.
        Unknown events retain bounded text. Malformed update JSON raises a
        sanitized CasaResponseError. EOF discards incomplete framing.

        Use contextlib.aclosing when breaking iteration early. Cancellation or
        aclose closes this response, never the caller's shared client session.
        """
        path = f"{_safe_home(home_id)}/casa_ai/events"
        _validate_cursor(after)
        async with aclosing(_stream_events(self.client, path, after)) as events:
            async for event in events:
                yield event

    async def request_details(self, home_id: str, request_id: str) -> RequestDetails:
        """VERIFIED (live GET, 2026-10). One request thread.

        Populated id, type, status, title, emoji, timestamps, unread flag,
        ``summary`` (scheduled_visit_count, total_spent, total_spent_display),
        messages (with sender avatar fields, attachments and the scheduling,
        availability, invoice and purchase-approval slots), plus visits,
        invoices, purchases and feedback.
        """
        path = f"{_safe_home(home_id)}/requests/{_safe_id(request_id)}"
        return _parse(RequestDetails, await self.client.get(path))

    # UNVERIFIED writes ------------------------------------------------------

    @unverified
    async def create_todo(self, home_id: str, body: CreateTodoBody) -> TodoDetail:
        """Legacy convenience return, accepting bare TodoDetail or a todo envelope.

        This intentionally discards needs_support_confirmation if supplied and
        doesn't require it. Use create_todo_result to retain and strictly validate
        the full envelope. Delegating to that method would
        break legacy responses without the flag. No automatic confirmation.
        """
        path = f"{_safe_home(home_id)}/todos"
        data = await self.client.post(path, json=_write_payload(body, StrictCreateTodoBody))
        if isinstance(data, dict) and isinstance(data.get("todo"), dict):
            data = data["todo"]
        return _parse(TodoDetail, data)

    @unverified
    async def create_todo_result(self, home_id: str, body: CreateTodoBody) -> CreateTodoResponse:
        """Create a to-do and retain the required support-confirmation flag.

        Wire format inferred statically from the app (LIKELY). Backend behavior UNVERIFIED.
        Requires todo and a strict Boolean needs_support_confirmation, with no
        missing/null default or bare-response fallback. Reuses TodoDetail.
        Omit absent attachments, preserve empty content and upload-ID arrays.
        Caller chooses execution. No upload, support confirmation or workflow retry.
        """
        path = f"{_safe_home(home_id)}/todos"
        data = await self.client.post(path, json=_write_payload(body, StrictCreateTodoBody))
        return _parse(CreateTodoResponse, data)

    @unverified
    async def send_request_message(
        self, home_id: str, request_id: str, body: SendRequestMessageRequest
    ) -> SendRequestMessageResponse:
        """Send one request-thread message only when explicitly called.

        Wire format inferred statically from the app (LIKELY). Backend behavior UNVERIFIED.
        Optional content, attachments.upload_ids and member role omit None.
        Explicit empty strings and lists are preserved. Privileged roles rejected.
        Required message envelope reuses RequestMessage, not CasaAIMessage.
        No upload chain, CasaAI send, MCP/HA action or workflow retry is added.
        """
        path = f"{_safe_home(home_id)}/requests/{_safe_id(request_id)}/messages"
        data = await self.client.post(path, json=_write_payload(body, SendRequestMessageRequest))
        return _parse(SendRequestMessageResponse, data)

    @unverified
    async def update_entity_properties(
        self, home_id: str, entity_id: str, body: UpdateEntityPropertiesRequest
    ) -> BasicMessageResponse:
        """PATCH inventory properties with String-valued property fields.

        Wire format inferred statically from the app (LIKELY). Backend behavior UNVERIFIED.
        Props is required, even when empty. Optional fields omit None recursively.
        Empty strings/lists and false selection flags are preserved, not interpreted
        as clears or replacements. Merge semantics and retry safety are unknown.
        Returns a status string envelope, not an entity. No automatic refresh.
        """
        path = f"{_safe_home(home_id, member=True)}/entity/{_safe_id(entity_id)}/props"
        data = await self.client.patch(
            path, json=_write_payload(body, UpdateEntityPropertiesRequest)
        )
        return _parse(BasicMessageResponse, data)
