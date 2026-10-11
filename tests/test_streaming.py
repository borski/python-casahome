"""Synthetic parser and aiohttp loopback tests, not live Casa/Firebase evidence.

No environment, SMS, or credential reads. The socket guard
rejects non-loopback connections. Tokens below are deliberately fake test data.
"""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import json
import logging
import socket
import traceback
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from pydantic import JsonValue

from casahome import (
    CasaApi,
    CasaApiError,
    CasaAuthError,
    CasaClient,
    CasaConnectionError,
    CasaResponseError,
    FirebaseAuth,
    is_unverified,
    streaming,
)
from casahome.const import CASA_APP, CASA_APP_VERSION, USER_AGENT
from casahome.streaming import (
    MAX_CURSOR_LENGTH,
    MAX_EVENT_BYTES,
    MAX_LINE_BYTES,
    CasaAIEvent,
    CasaAIResyncRequiredEvent,
    CasaAIThreadUpdateEvent,
    ServerSentEvent,
    SSEParser,
)

from .conftest import HOME_ID, TOKEN_PATH, FakeServer, Seen

PATH = f"/protected/home/{HOME_ID}/casa_ai/events"
TOKEN = {
    "access_token": "synthetic-access",
    "expires_in": "3600",
    "token_type": "Bearer",
    "refresh_token": "synthetic-refresh",
    "id_token": "synthetic-id-1",
    "user_id": "synthetic-user",
    "project_id": "synthetic-project",
}


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    getaddrinfo = socket.getaddrinfo

    def check(address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else address
        try:
            allowed = ipaddress.ip_address(host).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise AssertionError("Streaming tests forbid non-loopback network access")

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        check(address)
        connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        check(address)
        return connect_ex(sock, address)

    def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        check(host)
        return getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


@dataclass
class SSEReply:
    chunks: tuple[bytes, ...] = ()
    status: int = 200
    content_type: str = "text/event-stream"
    headers: dict[str, str] = field(default_factory=dict)
    header_delay: float = 0.0
    chunk_delay: float = 0.0
    hold: bool = False
    abort: bool = False


@dataclass
class StreamingFakeServer:
    """Extend the existing FakeServer by composition, with real chunked SSE."""

    http: FakeServer = field(default_factory=FakeServer)
    replies: list[SSEReply] = field(default_factory=list)
    seen: list[Seen] = field(default_factory=list)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    prepared: asyncio.Event = field(default_factory=asyncio.Event)

    def add(self, *chunks: bytes, **kwargs: Any) -> None:
        self.replies.append(SSEReply(chunks=chunks, **kwargs))

    async def handle(self, request: web.Request) -> web.StreamResponse:
        if request.path != PATH:
            return await self.http.handle(request)
        self.seen.append(
            Seen(
                request.method,
                request.path,
                dict(request.query),
                dict(request.headers),
                await request.text(),
            )
        )
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        await asyncio.sleep(reply.header_delay)
        response = web.StreamResponse(
            status=reply.status,
            headers={"Content-Type": reply.content_type, **reply.headers},
        )
        await response.prepare(request)
        self.prepared.set()
        if reply.status in (204, 304):
            # These statuses forbid a body. Never emit illegal trailing bytes.
            await response.write_eof()
            return response
        try:
            for chunk in reply.chunks:
                await asyncio.sleep(reply.chunk_delay)
                await response.write(chunk)
            if reply.hold:
                await self.release.wait()
            if reply.abort:
                assert request.transport is not None
                request.transport.close()
            else:
                await response.write_eof()
        except ConnectionResetError:
            pass  # Closing/cancelling a stream intentionally disconnects the reader.
        return response


@pytest.fixture
async def sse_server() -> AsyncIterator[StreamingFakeServer]:
    fake = StreamingFakeServer()
    fake.http.add("POST", TOKEN_PATH, payload=TOKEN)
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    async with TestServer(app, host="127.0.0.1") as server:
        fake.http.url = str(server.make_url("")).rstrip("/")
        try:
            yield fake
        finally:
            fake.release.set()


@dataclass
class StreamHarness:
    api: CasaApi
    client: CasaClient
    auth: FirebaseAuth
    session: aiohttp.ClientSession
    responses: list[aiohttp.ClientResponse]


@pytest.fixture
async def stream(sse_server: StreamingFakeServer) -> AsyncIterator[StreamHarness]:
    responses: list[aiohttp.ClientResponse] = []
    trace = aiohttp.TraceConfig()

    async def ended(
        session: aiohttp.ClientSession, context: Any, params: aiohttp.TraceRequestEndParams
    ) -> None:
        if params.url.path == PATH:
            responses.append(params.response)

    trace.on_request_end.append(ended)
    async with aiohttp.ClientSession(trace_configs=[trace]) as session:
        auth = FirebaseAuth(
            session, "synthetic-refresh", token_url=sse_server.http.url + TOKEN_PATH
        )
        client = CasaClient(session, auth, base_url=sse_server.http.url + "/")
        yield StreamHarness(CasaApi(client), client, auth, session, responses)


def parse(chunks: Iterator[bytes]) -> list[ServerSentEvent]:
    parser = SSEParser()
    return [event for chunk in chunks for event in parser.feed(chunk)]


def assert_closed(stream: StreamHarness) -> None:
    assert stream.responses
    assert all(response.closed for response in stream.responses)
    assert not stream.session.closed
    assert stream.session.connector is not None
    assert not stream.session.connector._acquired


async def collect(api: CasaApi, after: str | None = None) -> list[CasaAIEvent]:
    async with aclosing(api.casa_ai_events(HOME_ID, after)) as events:
        return [event async for event in events]


def test_guard_forbids_external_connections() -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match="non-loopback"):
        sock.connect(("192.0.2.1", 443))
    with socket.socket() as sock, pytest.raises(AssertionError, match="non-loopback"):
        sock.connect_ex(("192.0.2.1", 443))
    with pytest.raises(AssertionError, match="non-loopback"):
        socket.getaddrinfo("example.invalid", 443)


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
@pytest.mark.parametrize("size", [1, 2, 7, 16384])
def test_sse_framing_at_chunk_boundaries(ending: bytes, size: int) -> None:
    body = ending.join(
        [
            b": comment",
            b"retry: 100",
            b"unknown: ignored",
            b"event: notice",
            b"id: c:1",
            b"data: hello",
            b"data:  second: value",
            b"data",
            b"",
            b"data: next",
            b"",
            b"",
        ]
    )
    events = parse(iter(body[i : i + size] for i in range(0, len(body), size)))
    assert events == [
        ServerSentEvent("notice", "c:1", "hello\n second: value\n"),
        ServerSentEvent("message", "c:1", "next"),
    ]


def test_sse_ids_reset_ignore_nul_and_survive_blocks_without_data() -> None:
    body = (
        b"id: initial\n\nevent: dropped\n\nid: bad\x00id\ndata: one\n\n"
        b"id:\ndata: two\n\ndata: three\n\nid\n\ndata: four\n\n"
    )
    assert parse(iter([body])) == [
        ServerSentEvent("message", "initial", "one"),
        ServerSentEvent("message", "", "two"),
        ServerSentEvent("message", "", "three"),
        ServerSentEvent("message", "", "four"),
    ]


def test_empty_data_is_dispatched_and_event_field_overwrites() -> None:
    assert parse(iter([b"event: old\nevent: new\ndata:\n\nevent:\ndata: ok\n\n"])) == [
        ServerSentEvent("new", None, ""),
        ServerSentEvent("message", None, "ok"),
    ]


def test_bom_unicode_repair_and_case_sensitive_fields() -> None:
    body = b"\xef\xbb\xbfdata: caf\xc3\xa9\n\nData: ignored\ndata: \xff\xef\xbb\xbf\n\n"
    assert parse(iter(bytes([byte]) for byte in body)) == [
        ServerSentEvent("message", None, "caf\u00e9"),
        ServerSentEvent("message", None, "\ufffd\ufeff"),
    ]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b": heartbeat\n\n",
        b"id: x\n\n",
        b"event: x\n\n",
        b"data: dropped",
        b"data: dropped\n",
        b"data: dropped\r\n",
    ],
)
def test_no_dispatch_without_data_and_blank_terminator(body: bytes) -> None:
    assert parse(iter([body])) == []


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
@pytest.mark.parametrize("name", ["max_line_bytes", "max_event_bytes"])
def test_parser_rejects_invalid_limits(name: str, value: Any) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        SSEParser(**{name: value})


def test_line_limit_is_bytes_and_exact_boundary_is_allowed() -> None:
    parser = SSEParser(max_line_bytes=8)
    assert list(parser.feed(b"data: \xc3\xa9\n\n")) == [ServerSentEvent("message", None, "\u00e9")]
    with pytest.raises(CasaResponseError, match="line exceeds"):
        list(parser.feed(b"data: \xc3\xa9x"))


def test_unterminated_line_cannot_grow_past_limit() -> None:
    parser = SSEParser(max_line_bytes=4)
    assert list(parser.feed(b"xxxx")) == []
    with pytest.raises(CasaResponseError, match="line exceeds"):
        list(parser.feed(b"y"))


def test_event_limit_counts_ignored_fields_and_comments_and_resets() -> None:
    parser = SSEParser(max_event_bytes=9)
    assert list(parser.feed(b"data: x\n\ndata: y\n\n")) == [
        ServerSentEvent("message", None, "x"),
        ServerSentEvent("message", None, "y"),
    ]
    parser = SSEParser(max_event_bytes=9)
    assert list(parser.feed(b": hi\n")) == []
    with pytest.raises(CasaResponseError, match="event exceeds"):
        list(parser.feed(b"foo: x\n"))


def test_crlf_counts_as_one_delimiter_byte() -> None:
    parser = SSEParser(max_event_bytes=9)
    assert list(parser.feed(b"data: x\r\n\r\ndata: y\r\n\r\n")) == [
        ServerSentEvent("message", None, "x"),
        ServerSentEvent("message", None, "y"),
    ]


def test_lazy_parser_does_not_parse_past_a_yield() -> None:
    parser = SSEParser(max_line_bytes=32)
    events = parser.feed(b"event: resync_required\ndata: {}\n\n" + b"x" * 33)
    assert next(events).event == "resync_required"
    with pytest.raises(CasaResponseError, match="line exceeds"):
        next(events)


def test_async_generator_marker_is_preserved() -> None:
    assert inspect.isasyncgenfunction(CasaApi.casa_ai_events)
    assert not inspect.iscoroutinefunction(CasaApi.casa_ai_events)
    assert is_unverified(CasaApi.casa_ai_events)
    assert (CasaApi.casa_ai_events.__doc__ or "").startswith("UNVERIFIED")
    assert streaming.STREAM_READ_TIMEOUT == 60
    assert MAX_LINE_BYTES == 64 * 1024
    assert MAX_EVENT_BYTES == 256 * 1024


def test_separate_marker_handles_async_generator_without_docstring() -> None:
    async def generator() -> AsyncIterator[CasaAIEvent]:
        yield ServerSentEvent("message", None, "synthetic")

    assert generator.__doc__ is None
    assert streaming.unverified_stream(generator) is generator
    assert inspect.isasyncgenfunction(generator)
    assert is_unverified(generator)
    assert (generator.__doc__ or "").startswith("UNVERIFIED")


@pytest.mark.parametrize(
    "after", [None, "", "opaque:a/b?c=d&x=1%20#fragment +", "\u00e9", "x" * 2048]
)
async def test_get_headers_resume_and_cache(
    stream: StreamHarness, sse_server: StreamingFakeServer, after: str | None
) -> None:
    sse_server.add(b"data: hello\n\n")
    await stream.auth.get_id_token()
    assert await collect(stream.api, after) == [ServerSentEvent("message", after, "hello")]
    assert await collect(stream.api, after) == [ServerSentEvent("message", after, "hello")]
    assert len(sse_server.http.calls("POST", TOKEN_PATH)) == 1
    assert len(sse_server.seen) == 2
    for call in sse_server.seen:
        assert (call.method, call.path, call.body) == ("GET", PATH, "")
        assert call.headers["Accept"] == "text/event-stream"
        assert call.headers["Authorization"] == "Bearer synthetic-id-1"
        assert call.headers["X-Casa-App"] == CASA_APP
        assert call.headers["X-Casa-App-Version"] == CASA_APP_VERSION
        assert call.headers["User-Agent"] == USER_AGENT
        if after is None:
            assert call.query == {}
            assert "Last-Event-ID" not in call.headers
        else:
            assert call.query == {"after": after}
            assert call.headers["Last-Event-ID"] == after
    assert_closed(stream)


async def test_generator_is_lazy_and_does_not_bootstrap_or_write(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(b"data: hello\n\n")
    events = stream.api.casa_ai_events(HOME_ID)
    assert not sse_server.seen and not sse_server.http.seen
    assert await anext(events) == ServerSentEvent("message", None, "hello")
    await events.aclose()
    assert [call.method for call in sse_server.seen] == ["GET"]
    assert [call.path for call in sse_server.http.seen] == [TOKEN_PATH]
    assert_closed(stream)


@pytest.mark.parametrize(
    "home",
    ["", ".", "..", "../home", "h/x", "h?x", "h#x", "h%2f", "h x", "h\n", "\u00e9", None, True],
)
async def test_bad_home_rejected_before_auth_or_io(
    stream: StreamHarness, sse_server: StreamingFakeServer, home: Any
) -> None:
    with pytest.raises(ValueError):
        await anext(stream.api.casa_ai_events(home))
    assert not sse_server.seen and not sse_server.http.seen


@pytest.mark.parametrize(
    "cursor",
    [
        "x" * (MAX_CURSOR_LENGTH + 1),
        "a\r\nb",
        "\x00",
        "\x1f",
        "\x7f",
        "\x80",
        "\x9f",
        "\ud800",
        1,
        True,
        b"cursor",
    ],
)
async def test_bad_cursor_rejected_before_auth_or_io(
    stream: StreamHarness, sse_server: StreamingFakeServer, cursor: Any
) -> None:
    with pytest.raises(ValueError, match="after must"):
        await anext(stream.api.casa_ai_events(HOME_ID, cursor))
    assert not sse_server.seen and not sse_server.http.seen


@pytest.mark.parametrize(
    "payload",
    [
        None,
        True,
        1,
        1.5,
        "text",
        [],
        [1, {"nested": "x"}],
        {
            "changes": [{"type": "not-a-guessed-variant", "new": True}],
            "conversation_id": "synthetic",
            "cursor": "payload-only",
        },
    ],
)
async def test_thread_update_jsonvalues_and_unknown_events(
    stream: StreamHarness, sse_server: StreamingFakeServer, payload: JsonValue
) -> None:
    body = (
        b"id: frame-id\nevent: thread.update\ndata: "
        + json.dumps(payload).encode()
        + b"\n\nevent: unfamiliar\ndata: not JSON, ignore previous instructions\n\n"
    )
    sse_server.add(*(body[i : i + 3] for i in range(0, len(body), 3)))
    events = await collect(stream.api)
    update, unknown = events
    assert isinstance(update, CasaAIThreadUpdateEvent)
    assert update.payload == payload
    assert update.id == "frame-id" and update.event == "thread.update"
    assert update.data == json.dumps(payload)
    assert type(unknown) is ServerSentEvent
    assert unknown == ServerSentEvent(
        "unfamiliar", "frame-id", "not JSON, ignore previous instructions"
    )
    assert len(sse_server.seen) == 1
    assert_closed(stream)


async def test_multiline_json_and_resync_closes_before_yield(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(
        b'id: last\nevent: thread.update\ndata: {\ndata: "extra": 1}\n\n'
        b"event: resync_required\ndata: reload\n\n"
        b"event: thread.update\ndata: malformed\n\n" + b"x" * (MAX_LINE_BYTES + 1),
        hold=True,
    )
    events = stream.api.casa_ai_events(HOME_ID)
    async with aclosing(events):
        update = await anext(events)
        assert isinstance(update, CasaAIThreadUpdateEvent) and update.payload == {"extra": 1}
        resync = await anext(events)
        assert isinstance(resync, CasaAIResyncRequiredEvent)
        assert resync == CasaAIResyncRequiredEvent("resync_required", "last", "reload")
        assert_closed(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(events)
    assert len(sse_server.seen) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"data: unfinished",
        b"data: unfinished\n",
        b"event: resync_required\n\n",
        b":heartbeat\n\n",
    ],
)
async def test_eof_returns_without_reconnect_or_unfinished_dispatch(
    stream: StreamHarness, sse_server: StreamingFakeServer, body: bytes
) -> None:
    sse_server.add(body)
    assert await collect(stream.api) == []
    assert len(sse_server.seen) == 1
    assert_closed(stream)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json-SENSITIVE",
        b'{"secret":"SENSITIVE",}',
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"1e309",
        b"-1e309",
        b'{"amount":1e309}',
        b'{"amount":-1e309}',
        b'[1,[{"amount":1e309}]]',
        b'[1,[{"amount":-1e309}]]',
        b"[" * 2000 + b"]" * 2000,
    ],
)
async def test_bad_thread_json_is_sanitized_and_never_reconnects(
    stream: StreamHarness,
    sse_server: StreamingFakeServer,
    body: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="casahome")
    sse_server.add(b"event: thread.update\ndata: " + body + b"\n\n")
    with pytest.raises(CasaResponseError, match=r"Malformed thread\.update JSON") as exc:
        await collect(stream.api)
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert "SENSITIVE" not in "".join(traceback.format_exception(exc.value))
    assert "SENSITIVE" not in caplog.text
    assert len(sse_server.seen) == 1
    assert_closed(stream)


@pytest.mark.parametrize("kind", ["line", "event", "comment", "unknown_field"])
async def test_default_byte_limits_close_response(
    stream: StreamHarness, sse_server: StreamingFakeServer, kind: str
) -> None:
    body = {
        "line": b"data: " + b"x" * MAX_LINE_BYTES,
        "event": b"data: x\n" * (MAX_EVENT_BYTES // 8 + 1),
        "comment": b": x\n" * (MAX_EVENT_BYTES // 4 + 1),
        "unknown_field": b"xyz: x\n" * (MAX_EVENT_BYTES // 7 + 1),
    }[kind]
    sse_server.add(body)
    with pytest.raises(CasaResponseError, match="exceeds byte limit"):
        await collect(stream.api)
    assert len(sse_server.seen) == 1
    assert_closed(stream)


async def test_one_401_retry_uses_rotated_token_and_preserves_resume(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.http.add("POST", TOKEN_PATH, payload={**TOKEN, "id_token": "synthetic-id-2"})
    sse_server.add(b"private error body", status=401, hold=True)
    sse_server.add(b"data: ok\n\n")
    assert await collect(stream.api, "cursor") == [ServerSentEvent("message", "cursor", "ok")]
    assert len(sse_server.http.calls("POST", TOKEN_PATH)) == 2
    assert [call.headers["Authorization"] for call in sse_server.seen] == [
        "Bearer synthetic-id-1",
        "Bearer synthetic-id-2",
    ]
    assert all(call.query == {"after": "cursor"} for call in sse_server.seen)
    assert all(call.headers["Last-Event-ID"] == "cursor" for call in sse_server.seen)
    assert_closed(stream)


async def test_shared_session_raise_for_status_does_not_bypass_401_retry(
    sse_server: StreamingFakeServer,
) -> None:
    sse_server.http.add("POST", TOKEN_PATH, payload={**TOKEN, "id_token": "synthetic-id-2"})
    sse_server.add(status=401)
    sse_server.add(b"data: ok\n\n")
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        auth = FirebaseAuth(
            session, "synthetic-refresh", token_url=sse_server.http.url + TOKEN_PATH
        )
        client = CasaClient(session, auth, base_url=sse_server.http.url)
        assert await collect(CasaApi(client)) == [ServerSentEvent("message", None, "ok")]
        assert not session.closed
    assert len(sse_server.seen) == 2
    assert len(sse_server.http.calls("POST", TOKEN_PATH)) == 2


@pytest.mark.parametrize("client_timeout", [None, 0, 0.1, 30, 120])
async def test_transport_settings_bound_connect_but_not_stream_lifetime(
    stream: StreamHarness,
    sse_server: StreamingFakeServer,
    monkeypatch: pytest.MonkeyPatch,
    client_timeout: float | None,
) -> None:
    # CasaClient normally has a total timeout. None/0 also exercise the safe fallback.
    stream.client._timeout = aiohttp.ClientTimeout(total=client_timeout)
    captured: list[dict[str, Any]] = []
    original = stream.session.get

    def get(url: str, **kwargs: Any) -> Any:
        captured.append(kwargs)
        return original(url, **kwargs)

    monkeypatch.setattr(stream.session, "get", get)
    sse_server.add(b"data: ok\n\n")
    assert await collect(stream.api) == [ServerSentEvent("message", None, "ok")]
    timeout = captured[0]["timeout"]
    assert timeout.total is None
    assert timeout.connect == min(client_timeout or 60, 60)
    assert timeout.sock_read == 60
    assert captured[0]["allow_redirects"] is False
    assert captured[0]["raise_for_status"] is False
    assert_closed(stream)


async def test_reads_are_bounded_and_error_body_is_never_consumed(
    stream: StreamHarness,
    sse_server: StreamingFakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await stream.auth.get_id_token()
    sizes: list[int] = []
    original = aiohttp.StreamReader.read

    async def read(reader: aiohttp.StreamReader, n: int = -1) -> bytes:
        sizes.append(n)
        return await original(reader, n)

    monkeypatch.setattr(aiohttp.StreamReader, "read", read)
    sse_server.add(b"data: ok\n\n")
    assert await collect(stream.api) == [ServerSentEvent("message", None, "ok")]
    assert sizes and set(sizes) == {16 * 1024}
    sizes.clear()
    sse_server.replies.clear()
    sse_server.add(b"SENSITIVE", status=429, hold=True)
    with pytest.raises(CasaApiError):
        await collect(stream.api)
    assert sizes == []
    assert_closed(stream)


async def test_second_401_same_rejected_token_stops_after_two_attempts(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(b"SENSITIVE", status=401, hold=True)
    with pytest.raises(CasaAuthError) as exc:
        await collect(stream.api)
    assert "SENSITIVE" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert len(sse_server.seen) == 2
    assert len(sse_server.http.calls("POST", TOKEN_PATH)) == 2
    assert_closed(stream)


async def test_concurrent_stream_and_json_401s_share_one_refresh(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    count = 5
    sse_server.http.add("POST", TOKEN_PATH, payload={**TOKEN, "id_token": "synthetic-id-2"})
    for _ in range(count):
        sse_server.add(status=401, header_delay=0.03)
    sse_server.add(b"data: ok\n\n")
    sse_server.http.add("GET", "/synthetic/read", status=401, delay=0.06)
    sse_server.http.add("GET", "/synthetic/read", payload={"ok": True})
    results = await asyncio.gather(
        *(collect(stream.api) for _ in range(count)), stream.client.get("/synthetic/read")
    )
    assert results[:-1] == [[ServerSentEvent("message", None, "ok")]] * count
    assert results[-1] == {"ok": True}
    assert len(sse_server.http.calls("POST", TOKEN_PATH)) == 2
    assert len(sse_server.seen) == count * 2
    assert all(
        call.headers["Authorization"] == "Bearer synthetic-id-2" for call in sse_server.seen[count:]
    )
    assert_closed(stream)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 304, 400, 403, 404, 429, 500])
async def test_http_errors_are_status_only_without_body_read_or_retry(
    stream: StreamHarness, sse_server: StreamingFakeServer, status: int
) -> None:
    sse_server.add(
        b'{"error":{"code":"SENSITIVE","displayMessage":"synthetic-id-1"}}',
        status=status,
        headers={"Location": "/synthetic/redirect", "Retry-After": "1"},
        hold=True,
    )
    with pytest.raises(CasaApiError) as exc:
        await collect(stream.api)
    error = exc.value
    assert error.status == status and error.code == "stream_http_error"
    assert error.display_title == error.display_message == error.request_id == ""
    assert "SENSITIVE" not in str(error) and "synthetic-id-1" not in str(error)
    assert len(sse_server.seen) == 1
    assert [call.path for call in sse_server.http.seen] == [TOKEN_PATH]
    assert_closed(stream)


async def test_204_is_clean_termination(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(status=204, content_type="application/json")
    assert await collect(stream.api) == []
    assert len(sse_server.seen) == 1
    assert_closed(stream)


@pytest.mark.parametrize("content_type", ["application/json", "text/html", "text/plain"])
async def test_wrong_content_type_rejected_without_exposing_body(
    stream: StreamHarness, sse_server: StreamingFakeServer, content_type: str
) -> None:
    sse_server.add(b"SENSITIVE", content_type=content_type, hold=True)
    with pytest.raises(CasaResponseError, match="Expected text/event-stream") as exc:
        await collect(stream.api)
    assert "SENSITIVE" not in str(exc.value)
    assert_closed(stream)


async def test_sse_charset_parameter_accepted(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(b"data: ok\n\n", content_type="text/event-stream; charset=utf-8")
    assert await collect(stream.api) == [ServerSentEvent("message", None, "ok")]


@pytest.mark.parametrize("phase", ["headers", "body"])
async def test_timeout_closes_without_retry(
    stream: StreamHarness,
    sse_server: StreamingFakeServer,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    monkeypatch.setattr(streaming, "STREAM_READ_TIMEOUT", 0.02)
    if phase == "headers":
        sse_server.add(header_delay=0.1)
    else:
        sse_server.add(hold=True)
    with pytest.raises(CasaConnectionError, match="timed out") as exc:
        await collect(stream.api)
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert len(sse_server.seen) == 1
    assert not stream.session.closed
    if phase == "body":
        assert_closed(stream)


async def test_read_timeout_is_inactivity_not_total_lifetime(
    stream: StreamHarness, sse_server: StreamingFakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(streaming, "STREAM_READ_TIMEOUT", 0.04)
    sse_server.add(*([b": heartbeat\n\n"] * 5), b"data: ok\n\n", chunk_delay=0.015)
    assert await collect(stream.api) == [ServerSentEvent("message", None, "ok")]
    assert_closed(stream)


async def test_truncated_transfer_is_sanitized_connection_error(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(b"data: SENSITIVE", abort=True)
    with pytest.raises(CasaConnectionError, match="connection failed") as exc:
        await collect(stream.api)
    assert "SENSITIVE" not in str(exc.value)
    assert exc.value.__context__ is None
    assert len(sse_server.seen) == 1
    assert_closed(stream)


async def test_connection_refused_is_sanitized(
    stream: StreamHarness,
) -> None:
    await stream.auth.get_id_token()
    client = CasaClient(stream.session, stream.auth, base_url="http://127.0.0.1:1")
    with pytest.raises(CasaConnectionError, match="connection failed") as exc:
        await collect(CasaApi(client))
    assert "127.0.0.1" not in str(exc.value)
    assert exc.value.__context__ is None


async def test_auth_failure_is_sanitized_without_stream_request(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.http.routes[("POST", TOKEN_PATH)].clear()
    sse_server.http.add("POST", TOKEN_PATH, status=400, body="SENSITIVE synthetic-id-1")
    with pytest.raises(CasaAuthError) as exc:
        await collect(stream.api)
    assert str(exc.value) == "SSE authentication failed"
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert not sse_server.seen


async def test_auth_connection_failure_is_sanitized(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.http.routes[("POST", TOKEN_PATH)].clear()
    sse_server.http.add("POST", TOKEN_PATH, status=503, body="SENSITIVE")
    with pytest.raises(CasaConnectionError, match="SSE connection failed") as exc:
        await collect(stream.api)
    assert "SENSITIVE" not in str(exc.value)
    assert exc.value.__context__ is None
    assert not sse_server.seen


async def test_aclose_releases_held_response_and_shared_session_still_works(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(b"data: first\n\n", hold=True)
    events = stream.api.casa_ai_events(HOME_ID)
    assert await anext(events) == ServerSentEvent("message", None, "first")
    assert not stream.responses[0].closed
    await events.aclose()
    assert_closed(stream)
    sse_server.http.add("GET", "/synthetic/read", payload={"ok": True})
    assert await stream.client.get("/synthetic/read") == {"ok": True}


async def test_cancel_while_waiting_closes_response_not_session(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(hold=True)
    events = stream.api.casa_ai_events(HOME_ID)

    async def next_event() -> CasaAIEvent:
        return await anext(events)

    task = asyncio.create_task(next_event())
    await asyncio.wait_for(sse_server.prepared.wait(), timeout=1)
    # Trace callbacks run on the client after the response headers arrive.
    while not stream.responses:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await events.aclose()
    assert_closed(stream)
    sse_server.http.add("GET", "/synthetic/read", payload={"ok": True})
    assert await stream.client.get("/synthetic/read") == {"ok": True}


async def test_break_with_aclosing_releases_response(
    stream: StreamHarness, sse_server: StreamingFakeServer
) -> None:
    sse_server.add(b"data: first\n\n", hold=True)
    async with aclosing(stream.api.casa_ai_events(HOME_ID)) as events:
        async for event in events:
            assert event.data == "first"
            break
    assert_closed(stream)


async def test_stream_logs_never_include_content_tokens_or_cursor(
    stream: StreamHarness, sse_server: StreamingFakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="casahome")
    sse_server.add(b"data: SENSITIVE\n\n")
    assert (await collect(stream.api, "PRIVATE-CURSOR"))[0].data == "SENSITIVE"
    for needle in ("SENSITIVE", "synthetic-refresh", "synthetic-id-1", "PRIVATE-CURSOR"):
        assert needle not in caplog.text
