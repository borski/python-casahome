"""Low-level authenticated HTTP client for the Casa foundation API."""

from __future__ import annotations

import json as jsonlib
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import aiohttp

from ._base_http import wrap_connection_errors
from .auth import FirebaseAuth
from .const import (
    CASA_APP,
    CASA_APP_VERSION,
    DEFAULT_TIMEOUT_SECONDS,
    FOUNDATION_BASE_URL,
    USER_AGENT,
)
from .exceptions import CasaApiError, CasaAuthError

_LOGGER = logging.getLogger("casahome")


class CasaClient:
    """Sends authenticated requests and turns Casa error envelopes into exceptions.

    The client never owns the aiohttp session. Callers create and close it, which
    is what Home Assistant expects. For scripts, use :meth:`create`.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth: FirebaseAuth,
        *,
        base_url: str = FOUNDATION_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session
        self.auth = auth
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        refresh_token: str,
        *,
        base_url: str = FOUNDATION_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> AsyncIterator[CasaClient]:
        """Build a client with its own session. Convenience for scripts."""
        async with aiohttp.ClientSession() as session:
            auth = FirebaseAuth(session, refresh_token)
            yield cls(session, auth, base_url=base_url, timeout=timeout)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        """Send a request and return decoded JSON (or None for empty bodies)."""
        _LOGGER.debug("%s %s", method, path)
        status, body, used = await self._send(method, path, json=json, params=params)
        if status == 401:
            _LOGGER.debug("401 on %s %s, refreshing token and retrying once", method, path)
            self.auth.invalidate(used)
            status, body, _ = await self._send(method, path, json=json, params=params)
            if status == 401:
                raise CasaAuthError("Casa rejected the refreshed token (HTTP 401)")

        if status == 304 or (200 <= status < 300 and not body.strip()):
            return None
        if 200 <= status < 300:
            try:
                return jsonlib.loads(body)
            except ValueError as err:
                raise CasaApiError(status, "invalid_json", display_message=body[:200]) from err
        raise _api_error(status, body)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None,
        params: Mapping[str, str] | None,
    ) -> tuple[int, str, str]:
        token = await self.auth.get_id_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Casa-App": CASA_APP,
            "X-Casa-App-Version": CASA_APP_VERSION,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        kwargs: dict[str, Any] = {"headers": headers, "timeout": self._timeout}
        if json is not None:
            headers["Content-Type"] = "application/json"
            kwargs["data"] = jsonlib.dumps(json)
        if params:
            kwargs["params"] = dict(params)
        url = self._base_url + path
        async with (
            wrap_connection_errors(),
            self._session.request(method, url, **kwargs) as resp,
        ):
            return resp.status, await resp.text(), token

    async def get(self, path: str, *, params: Mapping[str, str] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, json: Any | None = None) -> Any:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, *, json: Any | None = None) -> Any:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)


def _api_error(status: int, body: str) -> CasaApiError:
    try:
        payload = jsonlib.loads(body)
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        err = payload["error"]
        return CasaApiError(
            status,
            str(err.get("code", "unknown")),
            str(err.get("displayTitle", "")),
            str(err.get("displayMessage", "")),
            str(err.get("requestId", "")),
        )
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        # Second observed shape: {"error": "Invalid user device info"}
        return CasaApiError(status, "unknown", display_message=payload["error"])
    return CasaApiError(status, "unknown", display_message=body[:500])
