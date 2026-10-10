"""Test harness: a real in-process aiohttp server standing in for Casa and Firebase.

Tests register canned responses per (method, path) and inspect what was sent.
No network, no mocking library to drift out of sync with aiohttp.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from casahome import CasaApi, CasaClient, FirebaseAuth

FIXTURES = Path(__file__).parent / "fixtures"
HOME_ID = "00000000-0000-4000-8000-000000000002"
TOKEN_PATH = "/v1/token"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@dataclass
class Canned:
    status: int = 200
    payload: Any = None
    body: str | None = None
    delay: float = 0.0


@dataclass
class Seen:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: str


@dataclass
class FakeServer:
    url: str = ""
    routes: dict[tuple[str, str], list[Canned]] = field(default_factory=lambda: defaultdict(list))
    seen: list[Seen] = field(default_factory=list)

    def add(self, method: str, path: str, **kw: Any) -> None:
        """Queue a response. The last one queued for a route repeats forever."""
        self.routes[(method, path)].append(Canned(**kw))

    def calls(self, method: str, path: str) -> list[Seen]:
        return [s for s in self.seen if s.method == method and s.path == path]

    async def handle(self, request: web.Request) -> web.Response:
        import asyncio

        body = await request.text()
        self.seen.append(
            Seen(request.method, request.path, dict(request.query), dict(request.headers), body)
        )
        queue = self.routes.get((request.method, request.path))
        if not queue:
            return web.Response(status=599, text=f"no route for {request.method} {request.path}")
        canned = queue.pop(0) if len(queue) > 1 else queue[0]
        if canned.delay:
            await asyncio.sleep(canned.delay)
        if canned.payload is not None:
            return web.json_response(canned.payload, status=canned.status)
        return web.Response(status=canned.status, text=canned.body or "")


@pytest.fixture
async def server() -> AsyncIterator[FakeServer]:
    fake = FakeServer()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    ts = TestServer(app)
    await ts.start_server()
    fake.url = str(ts.make_url("")).rstrip("/")
    try:
        yield fake
    finally:
        await ts.close()


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def auth(session: aiohttp.ClientSession, server: FakeServer) -> FirebaseAuth:
    return FirebaseAuth(session, "initial-refresh-token", token_url=server.url + TOKEN_PATH)


@pytest.fixture
def client(session: aiohttp.ClientSession, auth: FirebaseAuth, server: FakeServer) -> CasaClient:
    return CasaClient(session, auth, base_url=server.url)


@pytest.fixture
def api(client: CasaClient) -> CasaApi:
    return CasaApi(client)


@pytest.fixture
def token_ok(server: FakeServer) -> None:
    server.add("POST", TOKEN_PATH, payload=load("token_refresh.json"))
