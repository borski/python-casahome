"""Upload security regressions. Synthetic files and real loopback-only aiohttp requests."""

from __future__ import annotations

import asyncio
import inspect
import os
import stat
import threading
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from yarl import URL

from casahome import CasaApi, CasaApiError, CasaConnectionError, CasaRequestError, uploads
from casahome.writes import _read_bounded
from tests.conftest import HOME_ID, TOKEN_PATH, FakeServer
from tests.test_verified_writes import DOCUMENT_TYPES, STORAGE_PATH
from tests.test_verified_writes import storage as storage
from tests.test_write_contracts import CANARY
from tests.test_write_contracts import loopback_only as loopback_only
from tests.test_write_contracts import synthetic_token as synthetic_token


@pytest.fixture
def storage_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[aiohttp.ClientRequest], list[aiohttp.ClientSession]]:
    """Observe actual request construction without replacing ClientSession or transport."""
    original = aiohttp.ClientRequest.__init__
    requests: list[aiohttp.ClientRequest] = []
    sessions: list[aiohttp.ClientSession] = []

    def record(request: aiohttp.ClientRequest, *args: Any, **kwargs: Any) -> None:
        original(request, *args, **kwargs)
        if request.method == "PUT":
            session = kwargs["session"]
            assert isinstance(session, aiohttp.ClientSession)
            assert session.auth is None
            assert not session.headers
            assert isinstance(session.cookie_jar, aiohttp.DummyCookieJar)
            assert session.trust_env is False
            assert kwargs["ssl"] is True
            requests.append(request)
            sessions.append(session)

    monkeypatch.setattr(aiohttp.ClientRequest, "__init__", record)
    return requests, sessions


@pytest.mark.parametrize("credentials", ["bearer", "basic"])
@pytest.mark.filterwarnings("ignore:BasicAuth is deprecated:DeprecationWarning")
@pytest.mark.filterwarnings("ignore:The 'auth' parameter is deprecated:DeprecationWarning")
async def test_storage_never_inherits_caller_credentials(
    server: FakeServer,
    storage: str,
    credentials: str,
    storage_requests: tuple[list[aiohttp.ClientRequest], list[aiohttp.ClientSession]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    middleware_calls: list[str] = []

    async def caller_middleware(
        request: aiohttp.ClientRequest,
        handler: Callable[[aiohttp.ClientRequest], Awaitable[aiohttp.ClientResponse]],
    ) -> aiohttp.ClientResponse:
        middleware_calls.append(request.method)
        request.headers["X-Caller-Middleware"] = CANARY
        return await handler(request)

    headers = {"X-Casa-App": CANARY, "X-Casa-App-Version": CANARY, "X-Custom-Secret": CANARY}
    if credentials == "bearer":
        headers["Authorization"] = f"Bearer {CANARY}"
    options: dict[str, Any] = {}
    if "middlewares" in inspect.signature(aiohttp.ClientSession).parameters:
        options["middlewares"] = (caller_middleware,)
    # If trust_env ever leaks into storage, it must not consult real user netrc data.
    monkeypatch.setenv("NETRC", str(tmp_path / "synthetic-netrc"))
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    jar = aiohttp.CookieJar(unsafe=True)
    jar.update_cookies({"caller_cookie": CANARY}, response_url=URL(server.url))
    server.add("PUT", STORAGE_PATH, status=200)
    async with aiohttp.ClientSession(
        headers=headers,
        auth=aiohttp.BasicAuth("synthetic-user", CANARY) if credentials == "basic" else None,
        cookie_jar=jar,
        trust_env=True,
        **options,
    ) as caller:
        await uploads.put_storage_bytes(
            caller,
            storage,
            b"synthetic-content",
            "application/pdf",
            timeout=aiohttp.ClientTimeout(total=1),
        )
        assert not caller.closed
        assert caller.headers["X-Custom-Secret"] == CANARY
        assert len(caller.cookie_jar) == 1
        (constructed,), (owned,) = storage_requests
        assert owned is not caller and owned.closed
        for name in (
            "Authorization",
            "Cookie",
            "X-Casa-App",
            "X-Casa-App-Version",
            "X-Custom-Secret",
            "X-Caller-Middleware",
        ):
            assert name not in constructed.headers
    (put,) = server.calls("PUT", STORAGE_PATH)
    assert CANARY not in repr(put.headers)
    assert put.body == "synthetic-content"
    assert middleware_calls == []


@pytest.mark.parametrize("status", [200, 201, 401, 403, 500])
async def test_storage_owned_session_closed_on_success_and_failure(
    api: CasaApi,
    server: FakeServer,
    storage: str,
    status: int,
    storage_requests: tuple[list[aiohttp.ClientRequest], list[aiohttp.ClientSession]],
) -> None:
    server.add("PUT", STORAGE_PATH, status=status, body=CANARY)
    if status in (200, 201):
        await api.upload_document_content(storage, b"synthetic-content", "application/pdf")
    else:
        with pytest.raises(CasaApiError) as caught:
            await api.upload_document_content(storage, b"synthetic-content", "application/pdf")
        assert CANARY not in str(caught.value)
        assert "synthetic-session" not in "".join(traceback.format_exception(caught.value))
    _, sessions = storage_requests
    assert len(sessions) == 1 and sessions[0].closed
    assert not api.client._session.closed
    assert len(server.calls("PUT", STORAGE_PATH)) == 1


async def test_storage_session_closed_when_upload_cancelled(
    api: CasaApi,
    server: FakeServer,
    storage: str,
    storage_requests: tuple[list[aiohttp.ClientRequest], list[aiohttp.ClientSession]],
) -> None:
    server.add("PUT", STORAGE_PATH, delay=0.05)
    task = asyncio.create_task(
        api.upload_document_content(storage, b"synthetic", "application/pdf")
    )
    try:
        async with asyncio.timeout(1):
            while not storage_requests[1]:
                await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert storage_requests[1][0].closed
    assert not api.client._session.closed


async def test_storage_timeout_scrubbed_and_owned_session_closed(
    api: CasaApi,
    server: FakeServer,
    storage: str,
    storage_requests: tuple[list[aiohttp.ClientRequest], list[aiohttp.ClientSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server.add("PUT", STORAGE_PATH, delay=0.05)
    monkeypatch.setattr(api.client, "_timeout", aiohttp.ClientTimeout(total=0.01))
    with pytest.raises(CasaConnectionError) as caught:
        await api.upload_document_content(storage, b"synthetic", "application/pdf")
    assert "synthetic-session" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert storage_requests[1][0].closed
    assert not api.client._session.closed


async def test_storage_never_follows_redirects(
    api: CasaApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths: list[str] = []

    async def redirect(request: web.Request) -> web.Response:
        paths.append(request.path)
        return web.Response(status=307, headers={"Location": f"https://example.invalid/{CANARY}"})

    app = web.Application()
    app.router.add_put("/synthetic-upload", redirect)
    async with TestServer(app) as local:
        url = local.make_url("/synthetic-upload")
        monkeypatch.setattr(uploads, "STORAGE_UPLOAD_SCHEME", url.scheme)
        monkeypatch.setattr(uploads, "STORAGE_UPLOAD_HOST", url.host)
        monkeypatch.setattr(uploads, "STORAGE_UPLOAD_PORT", url.port)
        with pytest.raises(CasaApiError) as caught:
            await api.upload_document_content(str(url), b"synthetic", "application/pdf")
        assert caught.value.status == 307
        assert CANARY not in str(caught.value)
    assert paths == ["/synthetic-upload"]


@pytest.mark.parametrize("content,limit", [(b"x", 1), (b"synthetic", 9), (b"x" * 100_000, 100_000)])
async def test_regular_file_read_is_bounded(tmp_path: Path, content: bytes, limit: int) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(content)
    assert await _read_bounded(source, limit) == content


async def test_symlink_to_regular_file_allowed(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    link = tmp_path / "synthetic-link.pdf"
    link.symlink_to(source)
    assert await _read_bounded(link, 9) == b"synthetic"


@pytest.mark.parametrize("kind", ["empty", "directory", "fifo", "missing"])
async def test_special_or_empty_sources_rejected_before_upload_writes(
    api: CasaApi, server: FakeServer, tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "synthetic-source"
    if kind == "empty":
        source.touch()
    elif kind == "directory":
        source.mkdir()
    elif kind == "fifo":
        os.mkfifo(source)

    def denied_unbounded_read(path: Path) -> bytes:
        raise AssertionError("unbounded path read forbidden, including on synthetic FIFO")

    monkeypatch.setattr(Path, "read_bytes", denied_unbounded_read)
    server.add("GET", f"/protected/home/{HOME_ID}/documents/types", payload=DOCUMENT_TYPES)
    async with asyncio.timeout(1):
        with pytest.raises(CasaRequestError):
            await api.upload_document(HOME_ID, source, "synthetic.pdf")
    assert [(call.method, call.path) for call in server.seen if call.path != TOKEN_PATH] == [
        ("GET", f"/protected/home/{HOME_ID}/documents/types")
    ]


@pytest.mark.parametrize("mode", [stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK])
async def test_device_and_socket_types_rejected_without_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int
) -> None:
    source = tmp_path / "synthetic-device"
    source.write_bytes(b"synthetic")

    def device_info(descriptor: int) -> os.stat_result:
        return os.stat_result((mode, 0, 0, 1, 0, 0, 9, 0, 0, 0))

    def denied_read(descriptor: int, size: int) -> bytes:
        raise AssertionError("special file must never be read")

    monkeypatch.setattr(os, "fstat", device_info)
    monkeypatch.setattr(os, "read", denied_read)
    with pytest.raises(CasaRequestError):
        await _read_bounded(source, 9)


async def test_open_once_nonblocking_and_path_replacement_keeps_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "synthetic.pdf"
    replacement = tmp_path / "replacement.pdf"
    source.write_bytes(b"original")
    replacement.write_bytes(b"replacement")
    original_open, original_fstat = os.open, os.fstat
    descriptors: list[int] = []

    def open_once(path: str | os.PathLike[str], flags: int) -> int:
        assert flags & os.O_NONBLOCK
        assert flags & os.O_ACCMODE == os.O_RDONLY
        descriptor = original_open(path, flags)
        descriptors.append(descriptor)
        return descriptor

    def replace_after_fstat(descriptor: int) -> os.stat_result:
        info = original_fstat(descriptor)
        replacement.replace(source)
        return info

    monkeypatch.setattr(os, "open", open_once)
    monkeypatch.setattr(os, "fstat", replace_after_fstat)
    assert await _read_bounded(source, 8) == b"original"
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        original_fstat(descriptors[0])


async def test_growth_after_fstat_reads_only_limit_plus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "growing.pdf"
    source.write_bytes(b"small")
    original_fstat, original_read = os.fstat, os.read
    sizes: list[int] = []

    def grow_after_fstat(descriptor: int) -> os.stat_result:
        info = original_fstat(descriptor)
        with source.open("ab") as output:
            output.write(b"x" * 100_000)
        return info

    def short_read(descriptor: int, size: int) -> bytes:
        chunk = original_read(descriptor, min(size, 3))
        sizes.append(len(chunk))
        return chunk

    monkeypatch.setattr(os, "fstat", grow_after_fstat)
    monkeypatch.setattr(os, "read", short_read)
    with pytest.raises(CasaRequestError, match="max_file_size_bytes"):
        await _read_bounded(source, 16)
    assert sum(sizes) == 17


@pytest.mark.parametrize("failure", ["fstat", "read", "oversized"])
async def test_file_descriptor_closed_on_rejection_and_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    original_open, original_fstat = os.open, os.fstat
    descriptors: list[int] = []

    def record_open(path: str | os.PathLike[str], flags: int) -> int:
        descriptor = original_open(path, flags)
        descriptors.append(descriptor)
        return descriptor

    def failed_fstat(descriptor: int) -> os.stat_result:
        raise OSError(CANARY)

    def failed_read(descriptor: int, size: int) -> bytes:
        raise OSError(CANARY)

    monkeypatch.setattr(os, "open", record_open)
    if failure == "fstat":
        monkeypatch.setattr(os, "fstat", failed_fstat)
    elif failure == "read":
        monkeypatch.setattr(os, "read", failed_read)
    with pytest.raises(CasaRequestError) as caught:
        await _read_bounded(source, 1 if failure == "oversized" else 9)
    assert CANARY not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        original_fstat(descriptors[0])


async def test_read_timeout_bounds_await_and_worker_eventually_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    release, closed = threading.Event(), threading.Event()
    original_open, original_read, original_close = os.open, os.read, os.close
    descriptors: list[int] = []

    def record_open(path: str | os.PathLike[str], flags: int) -> int:
        descriptor = original_open(path, flags)
        descriptors.append(descriptor)
        return descriptor

    def delayed_read(descriptor: int, size: int) -> bytes:
        release.wait(timeout=0.5)
        return original_read(descriptor, size)

    def record_close(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor in descriptors:
            closed.set()

    monkeypatch.setattr(os, "open", record_open)
    monkeypatch.setattr(os, "read", delayed_read)
    monkeypatch.setattr(os, "close", record_close)
    try:
        with pytest.raises(CasaRequestError, match="file read timed out") as caught:
            await _read_bounded(source, 9, timeout=0.01)
        assert caught.value.__context__ is None
    finally:
        release.set()
        assert await asyncio.to_thread(closed.wait, 1)


async def test_cancelled_file_read_worker_closes_when_it_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic")
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    original_read, original_close = os.read, os.close
    descriptors: list[int] = []

    def delayed_read(descriptor: int, size: int) -> bytes:
        descriptors.append(descriptor)
        entered.set()
        release.wait(timeout=0.5)
        return original_read(descriptor, size)

    def record_close(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor in descriptors:
            closed.set()

    monkeypatch.setattr(os, "read", delayed_read)
    monkeypatch.setattr(os, "close", record_close)
    task = asyncio.create_task(_read_bounded(source, 9))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(closed.wait, 1)
