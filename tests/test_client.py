from __future__ import annotations

import asyncio
import logging

import pytest

from casahome import CasaApiError, CasaAuthError, CasaClient, CasaConnectionError, FirebaseAuth
from casahome.const import CASA_APP, CASA_APP_VERSION, USER_AGENT

from .conftest import TOKEN_PATH, FakeServer, load

PATH = "/protected/member/thing"
pytestmark = pytest.mark.usefixtures("token_ok")


async def test_headers(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, payload={"ok": True})
    assert await client.get(PATH) == {"ok": True}
    (call,) = server.calls("GET", PATH)
    assert call.headers["Authorization"] == "Bearer fake.id.token"
    assert call.headers["X-Casa-App"] == CASA_APP
    assert call.headers["X-Casa-App-Version"] == CASA_APP_VERSION
    assert call.headers["User-Agent"] == USER_AGENT
    assert call.headers["Accept"] == "application/json"


async def test_json_body(server: FakeServer, client: CasaClient) -> None:
    server.add("POST", PATH, payload={})
    await client.post(PATH, json={"a": 1})
    (call,) = server.calls("POST", PATH)
    assert call.headers["Content-Type"] == "application/json"
    assert call.body == '{"a": 1}'


async def test_401_refreshes_and_retries_once(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, status=401)
    server.add("GET", PATH, payload={"ok": True})
    assert await client.get(PATH) == {"ok": True}
    assert len(server.calls("POST", TOKEN_PATH)) == 2
    assert len(server.calls("GET", PATH)) == 2


async def test_second_401_raises(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, status=401)
    with pytest.raises(CasaAuthError):
        await client.get(PATH)
    assert len(server.calls("GET", PATH)) == 2


async def test_error_envelope(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, status=404, payload=load("error.json"))
    with pytest.raises(CasaApiError) as exc:
        await client.get(PATH)
    err = exc.value
    assert (err.status, err.code, err.display_title, err.display_message, err.request_id) == (
        404,
        "not_found",
        "Not found",
        "We couldn't find that.",
        "req_fake_000000",
    )


async def test_non_json_error(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, status=502, body="<html>bad gateway</html>")
    with pytest.raises(CasaApiError) as exc:
        await client.get(PATH)
    assert exc.value.code == "unknown"
    assert "bad gateway" in exc.value.display_message


async def test_non_json_success_raises_casa_error(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, status=200, body="<html>captive portal</html>")
    with pytest.raises(CasaApiError) as exc:
        await client.get(PATH)
    assert exc.value.code == "invalid_json"


async def test_304_and_empty_are_none(server: FakeServer, client: CasaClient) -> None:
    server.add("GET", PATH, status=304)
    server.add("GET", PATH, status=204)
    assert await client.get(PATH) is None
    assert await client.get(PATH) is None


async def test_timeout(server: FakeServer, session: object, auth: FirebaseAuth) -> None:
    import aiohttp

    assert isinstance(session, aiohttp.ClientSession)
    slow = CasaClient(session, auth, base_url=server.url, timeout=0.05)
    server.add("GET", PATH, payload={}, delay=0.5)
    with pytest.raises(CasaConnectionError):
        await slow.get(PATH)


async def test_connection_refused(session: object, auth: FirebaseAuth) -> None:
    import aiohttp

    assert isinstance(session, aiohttp.ClientSession)
    await auth.get_id_token()
    dead = CasaClient(session, auth, base_url="http://127.0.0.1:1")
    with pytest.raises(CasaConnectionError):
        await dead.get(PATH)


async def test_logs_never_contain_secrets(
    server: FakeServer, client: CasaClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="casahome")
    server.add("POST", PATH, payload={"secret": "s3cr3t"})
    await client.post(PATH, json={"body": "hidden"})
    for needle in ("fake.id.token", "initial-refresh-token", "fake-rotated", "s3cr3t", "hidden"):
        assert needle not in caplog.text
    assert PATH in caplog.text


async def test_string_error_shape(server: FakeServer, client: CasaClient) -> None:
    server.add("POST", PATH, status=400, payload={"error": "Invalid user device info"})
    with pytest.raises(CasaApiError) as exc:
        await client.post(PATH, json={})
    assert (exc.value.status, exc.value.display_message) == (400, "Invalid user device info")


async def test_concurrent_401s_refresh_once(server: FakeServer, client: CasaClient) -> None:
    for _ in range(5):
        server.add("GET", PATH, status=401)
    for _ in range(5):
        server.add("GET", PATH, payload={"ok": True})
    rotated = {**load("token_refresh.json"), "id_token": "fake.id.token.2"}
    server.add("POST", TOKEN_PATH, payload=rotated)
    results = await asyncio.gather(*(client.get(PATH) for _ in range(5)))
    assert results == [{"ok": True}] * 5
    # One initial refresh plus exactly one after the burst of 401s.
    assert len(server.calls("POST", TOKEN_PATH)) == 2
