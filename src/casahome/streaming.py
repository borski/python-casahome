"""Opt-in CasaAI SSE support.

The app uses GET, after plus Last-Event-ID, thread.update JSON, and a
terminal resync_required event. Live traffic (2026-10) confirmed the transport,
replay from an earlier cursor, and thread.update payloads carrying
``message.upsert`` changes. resync_required and other change types weren't seen.
Nothing in an event is executed, fetched, or treated as an instruction.
"""

from __future__ import annotations

import json
import math
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, TypeVar, cast

import aiohttp
from pydantic import JsonValue

from ._common import _parse
from .client import CasaClient
from .const import CASA_APP, CASA_APP_VERSION, USER_AGENT
from .exceptions import CasaApiError, CasaAuthError, CasaConnectionError, CasaResponseError
from .models.ai import CasaAIThreadUpdate

MAX_EVENT_BYTES = 256 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_CURSOR_LENGTH = 2048
STREAM_READ_TIMEOUT = 60.0
_CHUNK_BYTES = 16 * 1024


@dataclass(frozen=True)
class ServerSentEvent:
    """SSE fields. An absent or empty event field becomes the standard message type.

    id persists across dispatches. data is joined text, including unknown events.
    These values can contain member content. Don't log them indiscriminately.
    """

    event: str
    id: str | None
    data: str


@dataclass(frozen=True)
class CasaAIThreadUpdateEvent(ServerSentEvent):
    """thread.update with the decoded JSON kept as ``payload``.

    Call ``update()`` for the typed form. ``payload`` stays the fallback for
    anything the typed model doesn't cover.
    """

    event: Literal["thread.update"]
    payload: JsonValue

    def update(self) -> CasaAIThreadUpdate:
        """Typed payload. Raises a scrubbed CasaResponseError on schema drift.

        Unknown change types parse as ``CasaAIUnknownChange`` and don't fail.
        """
        return _parse(CasaAIThreadUpdate, self.payload)


@dataclass(frozen=True)
class CasaAIResyncRequiredEvent(ServerSentEvent):
    """Terminal resync signal. The caller decides how to reload and resume."""

    event: Literal["resync_required"]


CasaAIEvent = CasaAIThreadUpdateEvent | CasaAIResyncRequiredEvent | ServerSentEvent
_F = TypeVar("_F", bound=Callable[..., AsyncIterator[CasaAIEvent]])


def unverified_stream(func: _F) -> _F:
    """Mark an async generator without changing its identity or coroutine markers."""
    func.__casa_unverified__ = True  # type: ignore[attr-defined]
    func.__doc__ = (
        "UNVERIFIED (partial): live traffic (2026-10) confirmed GET/SSE transport, replay "
        "from an earlier cursor, and thread.update with message.upsert changes. "
        "resync_required and other change types aren't established.\n\n" + (func.__doc__ or "")
    ).rstrip()
    return func


def _validate_cursor(after: str | None) -> None:
    """Keep cursors opaque, but safe for the matching query and HTTP header."""
    if after is not None and (
        not isinstance(after, str)
        or len(after) > MAX_CURSOR_LENGTH
        or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in after)
        or any(0xD800 <= ord(c) <= 0xDFFF for c in after)
    ):
        raise ValueError("after must be a cursor of at most 2048 characters without controls")


class SSEParser:
    """Incremental bounded UTF-8 SSE parser. EOF discards an unfinished event.

    Supports LF, CRLF, and CR, comments, multiline data, a leading BOM, persistent
    IDs, and the standard empty ID reset. NUL IDs are ignored. Unknown fields,
    including retry, are ignored. Bounds include comments and unknown fields in
    each blank-line-delimited block. CRLF counts as one line-ending byte.
    feed is lazy, so stopping at a terminal event doesn't parse later bytes.
    """

    def __init__(
        self,
        *,
        last_event_id: str | None = None,
        max_event_bytes: int = MAX_EVENT_BYTES,
        max_line_bytes: int = MAX_LINE_BYTES,
    ) -> None:
        for value in (max_event_bytes, max_line_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("SSE byte limits must be positive integers")
        self._max_event_bytes = max_event_bytes
        self._max_line_bytes = max_line_bytes
        self._line = bytearray()
        self._block_bytes = 0
        self._skip_lf = False
        self._first_line = True
        self._event = ""
        self._id = last_event_id
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> Iterator[ServerSentEvent]:
        """Consume a bounded chunk and yield only blank-line-terminated events."""
        for byte in chunk:
            if self._skip_lf:
                self._skip_lf = False
                if byte == 10:
                    continue
            self._block_bytes += 1
            if self._block_bytes > self._max_event_bytes:
                raise CasaResponseError("SSE event exceeds byte limit")
            if byte in (10, 13):
                self._skip_lf = byte == 13
                event = self._consume_line()
                self._line.clear()
                if event is not None:
                    yield event
            else:
                if len(self._line) >= self._max_line_bytes:
                    raise CasaResponseError("SSE line exceeds byte limit")
                self._line.append(byte)

    def _consume_line(self) -> ServerSentEvent | None:
        line = self._line.decode("utf-8", errors="replace")
        if self._first_line:
            line = line.removeprefix("\ufeff")
            self._first_line = False
        if not line:
            event = (
                ServerSentEvent(self._event or "message", self._id, "\n".join(self._data))
                if self._data
                else None
            )
            self._event = ""
            self._data.clear()
            self._block_bytes = 0
            return event
        if line.startswith(":"):
            return None
        field, separator, value = line.partition(":")
        if separator:
            value = value.removeprefix(" ")
        if field == "event":
            self._event = value
        elif field == "id" and "\x00" not in value:
            self._id = value
        elif field == "data":
            self._data.append(value)
        return None


def _reject_constant(value: str) -> None:
    raise ValueError("Non-JSON numeric constant")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON number")
    return number


def _typed_event(event: ServerSentEvent) -> CasaAIEvent:
    if event.event == "resync_required":
        return CasaAIResyncRequiredEvent("resync_required", event.id, event.data)
    if event.event == "thread.update":
        # Don't retain a decoding exception as cause/context. It can hold raw data.
        try:
            payload = cast(
                JsonValue,
                json.loads(event.data, parse_constant=_reject_constant, parse_float=_finite_float),
            )
            valid = True
        except (ValueError, RecursionError):
            payload = None
            valid = False
        if not valid:
            raise CasaResponseError("Malformed thread.update JSON")
        return CasaAIThreadUpdateEvent("thread.update", event.id, event.data, payload)
    return event


@asynccontextmanager
async def _safe_stream_errors() -> AsyncIterator[None]:
    """Keep transport errors free of URLs, tokens, and remote body snippets."""
    error: CasaConnectionError | CasaAuthError | None = None
    try:
        yield
    except TimeoutError:
        error = CasaConnectionError("SSE request timed out")
    except (aiohttp.ClientError, CasaConnectionError):
        error = CasaConnectionError("SSE connection failed")
    except CasaAuthError:
        error = CasaAuthError("SSE authentication failed")
    if error is not None:
        # athrow() resumes this context manager under the caller's exception.
        # Clear that implicit context too, not only the displayed traceback.
        try:
            raise error from None
        finally:
            error.__context__ = None


async def _stream_events(
    client: CasaClient, path: str, after: str | None
) -> AsyncGenerator[CasaAIEvent, None]:
    """Internal fixed-route transport. The API validates the path and cursor.

    CasaClient has no public session/base/timeout accessors. Read those existing
    fields here only, without changing ownership or bypassing FirebaseAuth's
    cache and token-specific invalidation. JSON request() can't stream and its
    error-body helper exposes raw snippets, so neither is used for SSE bodies.
    """
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=min(client._timeout.total or STREAM_READ_TIMEOUT, STREAM_READ_TIMEOUT),
        sock_read=STREAM_READ_TIMEOUT,
    )
    async with _safe_stream_errors():
        for attempt in range(2):
            token = await client.auth.get_id_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Casa-App": CASA_APP,
                "X-Casa-App-Version": CASA_APP_VERSION,
                "User-Agent": USER_AGENT,
                "Accept": "text/event-stream",
            }
            params = None
            if after is not None:
                headers["Last-Event-ID"] = after
                params = {"after": after}
            async with client._session.get(
                client._base_url + path,
                headers=headers,
                params=params,
                timeout=timeout,
                allow_redirects=False,
                raise_for_status=False,
            ) as response:
                try:
                    if response.status == 401:
                        response.close()
                        if attempt:
                            raise CasaAuthError("Casa rejected the refreshed token (HTTP 401)")
                        client.auth.invalidate(token)
                        continue
                    if response.status == 204:
                        return
                    if response.status != 200:
                        # No error-body read, even for JSON. Status is safe metadata.
                        raise CasaApiError(response.status, "stream_http_error")
                    if response.content_type != "text/event-stream":
                        raise CasaResponseError("Expected text/event-stream response")
                    parser = SSEParser(last_event_id=after)
                    while chunk := await response.content.read(_CHUNK_BYTES):
                        for raw in parser.feed(chunk):
                            event = _typed_event(raw)
                            if isinstance(event, CasaAIResyncRequiredEvent):
                                response.close()
                                yield event
                                return
                            yield event
                    return
                finally:
                    response.close()
