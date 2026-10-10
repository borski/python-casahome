"""Firebase refresh-token auth for the Casa API.

Casa signs members in with Firebase Phone Auth. SMS sign-in can't be reproduced
off-device (Firebase requires APNs app verification), so this library starts
from a refresh token captured from the app and exchanges it for short-lived
ID tokens via the standard Firebase secure token endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

import aiohttp
from pydantic import ValidationError

from ._base_http import wrap_connection_errors
from .const import (
    DEFAULT_TIMEOUT_SECONDS,
    FIREBASE_API_KEY,
    FIREBASE_BUNDLE_ID,
    FIREBASE_CLIENT_VERSION,
    FIREBASE_GMP_ID,
    SECURETOKEN_URL,
    TOKEN_REFRESH_LEEWAY_SECONDS,
)
from .exceptions import CasaAuthError, CasaConnectionError, CasaError
from .models._base import CasaModel

_LOGGER = logging.getLogger("casahome")

_FATAL_REFRESH_ERRORS = frozenset(
    {"TOKEN_EXPIRED", "USER_DISABLED", "USER_NOT_FOUND", "INVALID_REFRESH_TOKEN"}
)


class TokenResponse(CasaModel):
    """Response from ``securetoken.googleapis.com/v1/token``."""

    access_token: str
    expires_in: str
    token_type: str
    refresh_token: str
    id_token: str
    user_id: str
    project_id: str


class FirebaseAuth:
    """Exchanges a Firebase refresh token for ID tokens, caching until near expiry.

    Firebase may rotate the refresh token on any refresh. Pass
    ``on_refresh_token_rotated`` (sync or async) to persist the new one, or read
    :attr:`refresh_token` after use.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        *,
        api_key: str = FIREBASE_API_KEY,
        token_url: str = SECURETOKEN_URL,
        on_refresh_token_rotated: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> None:
        if not refresh_token:
            raise CasaAuthError("refresh_token is required")
        self._session = session
        self._refresh_token = refresh_token
        self._api_key = api_key
        self._token_url = token_url
        self._id_token: str | None = None
        self._expires_at: float = 0.0
        self._user_id: str | None = None
        self._lock = asyncio.Lock()
        self._on_rotated = on_refresh_token_rotated

    @property
    def refresh_token(self) -> str:
        """The current refresh token, possibly rotated by Firebase."""
        return self._refresh_token

    @property
    def user_id(self) -> str | None:
        """Firebase uid, known after the first refresh."""
        return self._user_id

    def _token_is_fresh(self) -> bool:
        return (
            self._id_token is not None
            and self._expires_at - time.monotonic() > TOKEN_REFRESH_LEEWAY_SECONDS
        )

    async def get_id_token(self) -> str:
        """Return a valid ID token, refreshing if it expires within the leeway."""
        if self._token_is_fresh():
            assert self._id_token is not None
            return self._id_token
        async with self._lock:
            if not self._token_is_fresh():
                await self._refresh_locked()
            assert self._id_token is not None
            return self._id_token

    def invalidate(self, token: str | None = None) -> None:
        """Drop the cached ID token so the next call refreshes.

        Pass the token that was rejected. If another request already replaced
        it, this is a no-op, so a burst of concurrent 401s costs one refresh.
        """
        if token is not None and token != self._id_token:
            return
        self._id_token = None
        self._expires_at = 0.0

    async def refresh(self) -> TokenResponse:
        """Force a refresh regardless of cached token state."""
        async with self._lock:
            return await self._refresh_locked()

    async def _refresh_locked(self) -> TokenResponse:
        _LOGGER.debug("Refreshing Firebase ID token")
        headers = {
            "X-Ios-Bundle-Identifier": FIREBASE_BUNDLE_ID,
            "X-Firebase-GMPID": FIREBASE_GMP_ID,
            "X-Client-Version": FIREBASE_CLIENT_VERSION,
        }
        data = {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
        async with (
            wrap_connection_errors(),
            self._session.post(
                self._token_url,
                params={"key": self._api_key},
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS),
            ) as resp,
        ):
            text = await resp.text()
            if resp.status >= 400:
                raise _auth_error(resp.status, text)
            try:
                token = TokenResponse.model_validate_json(text)
            except ValidationError as err:
                # A 200 that isn't a token response is a proxy or portal, not a bad credential.
                raise CasaConnectionError(
                    f"Token endpoint returned an unexpected body: {text[:200]}"
                ) from err

        self._id_token = token.id_token
        previous = self._refresh_token
        self._refresh_token = token.refresh_token or self._refresh_token
        self._user_id = token.user_id
        try:
            lifetime = int(token.expires_in)
        except ValueError:
            lifetime = 3600
        self._expires_at = time.monotonic() + lifetime
        if self._refresh_token != previous and self._on_rotated is not None:
            await self._notify_rotated(self._refresh_token)
        return token

    async def _notify_rotated(self, new_token: str) -> None:
        """Run the rotation callback. Its failures are logged, never raised.

        Auth already succeeded at this point. A broken persistence hook must
        not fail the request that triggered the refresh.
        """
        assert self._on_rotated is not None
        try:
            result = self._on_rotated(new_token)
            if result is not None:
                await result
        except Exception:
            _LOGGER.exception("on_refresh_token_rotated callback failed; new token not persisted")


def _auth_error(status: int, body: str) -> CasaError:
    """Map a token endpoint failure.

    Only 4xx means the credential itself is bad. 5xx is Google having a bad
    day and must not trigger reauth in Home Assistant.
    """
    message = ""
    try:
        payload = json.loads(body)
        error = payload.get("error", {})
        message = error.get("message", "") if isinstance(error, dict) else str(error)
    except (ValueError, AttributeError):
        pass
    if message in _FATAL_REFRESH_ERRORS:
        return CasaAuthError(message)
    excerpt = message or body[:200]
    if status >= 500 or status == 429:
        return CasaConnectionError(f"Token endpoint unavailable (HTTP {status}): {excerpt}")
    return CasaAuthError(f"Token refresh failed (HTTP {status}): {excerpt}")
