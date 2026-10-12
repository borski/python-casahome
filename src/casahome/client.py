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
        retry_on_401: bool | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Send a request and return decoded JSON (or None for empty bodies).

        ``retry_on_401`` defaults to True for GET only. Writes (POST, PATCH,
        PUT, DELETE) default to a single attempt: a 401 after the server may have
        acted would turn a retry into a duplicate write. Non-retrying requests
        start with a force-refreshed ID token instead, so an expiring token
        can't trigger the 401 in the first place. A 401 still invalidates the
        rejected token and raises ``CasaAuthError``.

        ``headers`` adds per-request headers, such as ``Idempotency-Key``. They
        can't override the auth or app identity headers.

        Non-GET error bodies never fall back to raw response text. Only the
        structured error envelope fields are kept, since a write's error body
        could echo the private content that was sent.
        """
        retry = method == "GET" if retry_on_401 is None else retry_on_401
        # Preparation GETs can precede destructive writes. Don't reflect raw
        # upstream bodies when callers explicitly choose single-attempt mode.
        scrub = method != "GET" or not retry
        _LOGGER.debug("%s %s", method, path)
        if not retry:
            await self.auth.refresh()
        status, body, used = await self._send(
            method, path, json=json, params=params, extra_headers=headers
        )
        if status == 401:
            self.auth.invalidate(used)
            if not retry:
                raise CasaAuthError(f"Casa rejected the ID token (HTTP 401) on {method}")
            _LOGGER.debug("401 on %s %s, refreshing token and retrying once", method, path)
            status, body, _ = await self._send(
                method, path, json=json, params=params, extra_headers=headers
            )
            if status == 401:
                raise CasaAuthError("Casa rejected the refreshed token (HTTP 401)")

        if status == 304 or (200 <= status < 300 and not body.strip()):
            return None
        if 200 <= status < 300:
            try:
                return jsonlib.loads(body)
            except ValueError:
                display = "" if scrub else body[:200]
            # Raised outside the handler so the decode error's context is dropped.
            raise CasaApiError(status, "invalid_json", display_message=display)
        raise _api_error(status, body, raw_fallback=not scrub)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None,
        params: Mapping[str, str] | None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[int, str, str]:
        token = await self.auth.get_id_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Casa-App": CASA_APP,
            "X-Casa-App-Version": CASA_APP_VERSION,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        reserved = {name.lower() for name in (*headers, "Content-Type")}
        for name, value in (extra_headers or {}).items():
            if name.lower() not in reserved:
                headers[name] = value
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

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        return await self.request("GET", path, params=params, retry_on_401=retry_on_401)

    async def post(self, path: str, *, json: Any | None = None, retry_on_401: bool = False) -> Any:
        return await self.request("POST", path, json=json, retry_on_401=retry_on_401)

    async def patch(self, path: str, *, json: Any | None = None) -> Any:
        return await self.request("PATCH", path, json=json, retry_on_401=False)

    async def put(self, path: str, *, json: Any | None = None) -> Any:
        return await self.request("PUT", path, json=json, retry_on_401=False)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path, retry_on_401=False)


def _api_error(status: int, body: str, *, raw_fallback: bool = True) -> CasaApiError:
    try:
        payload = jsonlib.loads(body)
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        # Both key styles are observed live: camelCase on most routes and
        # snake_case on save_and_publish catalog errors (2026-10).
        err = payload["error"]
        return CasaApiError(
            status,
            str(err.get("code", "unknown")),
            _error_field(err, "displayTitle", "display_title"),
            _error_field(err, "displayMessage", "display_message"),
            _error_field(err, "requestId", "request_id"),
        )
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        # Second observed shape: {"error": "Invalid user device info"}
        return CasaApiError(status, "unknown", display_message=payload["error"])
    return CasaApiError(status, "unknown", display_message=body[:500] if raw_fallback else "")


def _error_field(err: dict[str, Any], camel: str, snake: str) -> str:
    """Return the camelCase key if present, else the snake_case key, else ""."""
    value = err[camel] if camel in err else err.get(snake, "")
    return str(value)
