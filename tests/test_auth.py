from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import parse_qs

import pytest

from casahome import CasaAuthError, CasaConnectionError, FirebaseAuth
from casahome.const import FIREBASE_API_KEY, FIREBASE_BUNDLE_ID, FIREBASE_GMP_ID

from .conftest import TOKEN_PATH, FakeServer, load


def _refreshes(server: FakeServer) -> int:
    return len(server.calls("POST", TOKEN_PATH))


@pytest.mark.usefixtures("token_ok")
async def test_refresh_stores_tokens_and_rotation(auth: FirebaseAuth) -> None:
    assert await auth.get_id_token() == "fake.id.token"
    assert auth.refresh_token == "fake-rotated-refresh-token"
    assert auth.user_id == "fakeFirebaseUid0000000000000"


@pytest.mark.usefixtures("token_ok")
async def test_refresh_request_shape(server: FakeServer, auth: FirebaseAuth) -> None:
    await auth.get_id_token()
    (call,) = server.calls("POST", TOKEN_PATH)
    assert call.query == {"key": FIREBASE_API_KEY}
    assert parse_qs(call.body) == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["initial-refresh-token"],
    }
    assert call.headers["X-Ios-Bundle-Identifier"] == FIREBASE_BUNDLE_ID
    assert call.headers["X-Firebase-GMPID"] == FIREBASE_GMP_ID


@pytest.mark.usefixtures("token_ok")
async def test_fresh_token_is_cached(server: FakeServer, auth: FirebaseAuth) -> None:
    await auth.get_id_token()
    await auth.get_id_token()
    assert _refreshes(server) == 1


@pytest.mark.usefixtures("token_ok")
async def test_rotated_token_used_on_next_refresh(server: FakeServer, auth: FirebaseAuth) -> None:
    await auth.get_id_token()
    await auth.refresh()
    assert "fake-rotated-refresh-token" in server.calls("POST", TOKEN_PATH)[1].body


@pytest.mark.usefixtures("token_ok")
async def test_refreshes_when_expired(server: FakeServer, auth: FirebaseAuth) -> None:
    await auth.get_id_token()
    auth._expires_at = time.monotonic() - 1
    await auth.get_id_token()
    assert _refreshes(server) == 2


@pytest.mark.usefixtures("token_ok")
async def test_refreshes_within_leeway(server: FakeServer, auth: FirebaseAuth) -> None:
    await auth.get_id_token()
    auth._expires_at = time.monotonic() + 30
    await auth.get_id_token()
    assert _refreshes(server) == 2


async def test_concurrent_callers_refresh_once(server: FakeServer, auth: FirebaseAuth) -> None:
    server.add("POST", TOKEN_PATH, payload=load("token_refresh.json"), delay=0.05)
    tokens = await asyncio.gather(*(auth.get_id_token() for _ in range(10)))
    assert set(tokens) == {"fake.id.token"}
    assert _refreshes(server) == 1


@pytest.mark.parametrize(
    "message", ["TOKEN_EXPIRED", "USER_DISABLED", "USER_NOT_FOUND", "INVALID_REFRESH_TOKEN"]
)
async def test_fatal_errors(server: FakeServer, auth: FirebaseAuth, message: str) -> None:
    server.add("POST", TOKEN_PATH, status=400, payload={"error": {"code": 400, "message": message}})
    with pytest.raises(CasaAuthError, match=f"^{message}$"):
        await auth.get_id_token()


@pytest.mark.parametrize("status", [500, 503, 429])
async def test_transient_errors_are_not_auth_errors(
    server: FakeServer, auth: FirebaseAuth, status: int
) -> None:
    # A Google outage must not trigger reauth in Home Assistant.
    server.add("POST", TOKEN_PATH, status=status, body="boom")
    with pytest.raises(CasaConnectionError, match=f"HTTP {status}"):
        await auth.get_id_token()


async def test_unknown_4xx_is_auth_error(server: FakeServer, auth: FirebaseAuth) -> None:
    server.add("POST", TOKEN_PATH, status=400, payload={"error": {"message": "WEIRD"}})
    with pytest.raises(CasaAuthError, match="HTTP 400"):
        await auth.get_id_token()


def test_empty_refresh_token_rejected() -> None:
    with pytest.raises(CasaAuthError):
        FirebaseAuth(None, "")  # type: ignore[arg-type]


async def test_non_json_200_is_connection_error(server: FakeServer, auth: FirebaseAuth) -> None:
    server.add("POST", TOKEN_PATH, status=200, body="<html>captive portal</html>")
    with pytest.raises(CasaConnectionError, match="unexpected body"):
        await auth.get_id_token()


@pytest.mark.usefixtures("token_ok")
async def test_invalidate_ignores_stale_token(auth: FirebaseAuth) -> None:
    current = await auth.get_id_token()
    auth.invalidate("some-older-token")
    assert auth._id_token == current
    auth.invalidate(current)
    assert auth._id_token is None


async def test_rotation_callback_async(server: FakeServer, session: object) -> None:
    server.add("POST", TOKEN_PATH, payload=load("token_refresh.json"))
    seen: list[str] = []

    async def persist(token: str) -> None:
        seen.append(token)

    auth = FirebaseAuth(
        session,  # type: ignore[arg-type]
        "initial-refresh-token",
        token_url=server.url + TOKEN_PATH,
        on_refresh_token_rotated=persist,
    )
    await auth.get_id_token()
    assert seen == ["fake-rotated-refresh-token"]


async def test_rotation_callback_sync_and_not_called_when_unchanged(
    server: FakeServer, session: object
) -> None:
    payload = {**load("token_refresh.json"), "refresh_token": "same-token"}
    server.add("POST", TOKEN_PATH, payload=payload)
    seen: list[str] = []
    auth = FirebaseAuth(
        session,  # type: ignore[arg-type]
        "same-token",
        token_url=server.url + TOKEN_PATH,
        on_refresh_token_rotated=seen.append,
    )
    await auth.refresh()
    assert seen == []


async def test_rotation_callback_failure_does_not_break_auth(
    server: FakeServer, session: object, caplog: pytest.LogCaptureFixture
) -> None:
    server.add("POST", TOKEN_PATH, payload=load("token_refresh.json"))

    async def broken(token: str) -> None:
        raise OSError("disk full")

    auth = FirebaseAuth(
        session,  # type: ignore[arg-type]
        "initial-refresh-token",
        token_url=server.url + TOKEN_PATH,
        on_refresh_token_rotated=broken,
    )
    with caplog.at_level(logging.ERROR, logger="casahome"):
        assert await auth.get_id_token() == "fake.id.token"
    assert "callback failed" in caplog.text
    assert "fake-rotated-refresh-token" not in caplog.text
