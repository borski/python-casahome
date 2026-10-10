"""High-level Casa API.

Confidence per method:

- VERIFIED: observed in captured app traffic. Path, method, and body shape known.
- UNVERIFIED: path and response schema recovered from the app binary. The HTTP
  method and any query parameters are best guesses. Expect 404/405 until
  confirmed against live traffic.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .client import CasaClient
from .const import APP_MARKETING_VERSION, CASA_APP_VERSION, CASA_DEVICE_APP
from .exceptions import CasaResponseError
from .models import (
    Bootstrap,
    CreateTodoBody,
    HomeBadgeCounts,
    HomeDetailsResponse,
    MailboxMailItemsResponse,
    MailboxOverviewResponse,
    MemberCredits,
    PackagesResponse,
    RequestDetails,
    RequestsResponse,
    TodoDetail,
    UserDeviceRequest,
    VisitsCalendarResponse,
    WeatherResponse,
)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
M = TypeVar("M", bound=BaseModel)


def _parse(model: type[M], data: Any) -> M:
    """Validate a response, turning schema drift into a library error."""
    try:
        return model.model_validate(data)
    except ValidationError as err:
        raise CasaResponseError(
            f"Unexpected {model.__name__} response: {err.error_count()} validation error(s)"
        ) from err


_UNVERIFIED_NOTE = (
    "UNVERIFIED: inferred path, HTTP method supported by static disassembly (LIKELY). "
    "Not yet observed live."
)


def unverified(func: F) -> F:
    """Mark a method whose path or HTTP method hasn't been seen in real traffic."""
    func.__casa_unverified__ = True  # type: ignore[attr-defined]
    func.__doc__ = f"{_UNVERIFIED_NOTE}\n\n{func.__doc__ or ''}".rstrip()
    return func


def is_unverified(method: Callable[..., Any]) -> bool:
    return bool(getattr(method, "__casa_unverified__", False))


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


def _home(home_id: str) -> str:
    """Base for most per-home endpoints (disassembly, 2026-10-10)."""
    return f"/protected/home/{home_id}"


def _member_home(home_id: str) -> str:
    """Base for inventory, entity, room, and story endpoints only."""
    return f"/protected/member/home/{home_id}"


class CasaApi:
    """Typed wrappers around Casa member endpoints."""

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
        """VERIFIED. User profile, homes, badge counts, app update info."""
        device = device or self.default_device()
        data = await self.client.post(
            "/protected/member/bootstrap",
            json={"user_device": device.model_dump(mode="json")},
        )
        return _parse(Bootstrap, data)

    async def onboarding_details(self, home_id: str) -> dict[str, Any] | None:
        """VERIFIED path and method. Body shape not yet captured, so returned raw."""
        data = await self.client.get(f"/protected/home/{home_id}/onboarding/details")
        return data if isinstance(data, dict) else None

    # UNVERIFIED reads -------------------------------------------------------

    @unverified
    async def home_details(self, home_id: str) -> HomeDetailsResponse:
        """Stories, rooms, and inventory entities."""
        data = await self.client.get(f"{_member_home(home_id)}/inventory/v3")
        return _parse(HomeDetailsResponse, data)

    @unverified
    async def badge_counts(self, home_id: str) -> HomeBadgeCounts:
        """Cheap poll for unread counts per feature."""
        data = await self.client.get(f"{_home(home_id)}/badge_counts")
        return _parse(HomeBadgeCounts, data)

    @unverified
    async def weather(self, home_id: str) -> WeatherResponse:
        data = await self.client.get(f"{_home(home_id)}/weather")
        return _parse(WeatherResponse, data)

    @unverified
    async def requests_tab(self, home_id: str) -> RequestsResponse:
        """Requests, tasks, and to-dos lanes in one call."""
        data = await self.client.get(f"{_home(home_id)}/requests_tab")
        return _parse(RequestsResponse, data)

    @unverified
    async def request_details(self, home_id: str, request_id: str) -> RequestDetails:
        """A single request thread: messages, visits, invoices, purchases."""
        data = await self.client.get(f"{_home(home_id)}/requests/{request_id}")
        return _parse(RequestDetails, data)

    @unverified
    async def calendar(
        self, home_id: str, start: datetime | int, end: datetime | int
    ) -> VisitsCalendarResponse:
        """Visit calendar between two bounds.

        Static disassembly shows ``start_time`` and ``end_time`` query items
        containing stringified Swift integers. Their time units aren't verified.

        Accepts aware datetimes or epoch seconds. Naive datetimes are rejected,
        since guessing a zone silently shifts the window. Datetime conversion
        assumes Unix seconds pending traffic confirmation.
        """
        data = await self.client.get(
            f"{_home(home_id)}/calendar",
            params={"start_time": str(_epoch(start)), "end_time": str(_epoch(end))},
        )
        return _parse(VisitsCalendarResponse, data)

    @unverified
    async def credits_summary(self, home_id: str) -> MemberCredits:
        data = await self.client.get(f"{_home(home_id)}/credits/summary")
        return _parse(MemberCredits, data)

    @unverified
    async def mailbox(self, home_id: str) -> MailboxOverviewResponse:
        data = await self.client.get(f"{_home(home_id)}/mailbox")
        return _parse(MailboxOverviewResponse, data)

    @unverified
    async def mail_items(self, home_id: str) -> MailboxMailItemsResponse:
        data = await self.client.get(f"{_home(home_id)}/mailbox/mail_items")
        return _parse(MailboxMailItemsResponse, data)

    @unverified
    async def packages(self, home_id: str) -> PackagesResponse:
        data = await self.client.get(f"{_home(home_id)}/packages/v3")
        return _parse(PackagesResponse, data)

    # UNVERIFIED writes ------------------------------------------------------

    @unverified
    async def create_todo(self, home_id: str, body: CreateTodoBody) -> TodoDetail:
        """Create a to-do. Response wrapper shape (CreateTodoResponse) unknown;
        accepts either a bare TodoDetail or ``{"todo": {...}}``."""
        data = await self.client.post(
            f"{_home(home_id)}/todos", json=body.model_dump(mode="json", exclude_none=True)
        )
        if isinstance(data, dict) and isinstance(data.get("todo"), dict):
            data = data["todo"]
        return _parse(TodoDetail, data)
