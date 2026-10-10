"""Small shared HTTP helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiohttp

from .exceptions import CasaConnectionError


@asynccontextmanager
async def wrap_connection_errors() -> AsyncIterator[None]:
    """Translate aiohttp network failures and timeouts into CasaConnectionError."""
    try:
        yield
    except TimeoutError as err:
        raise CasaConnectionError("Request timed out") from err
    except aiohttp.ClientError as err:
        raise CasaConnectionError(str(err) or type(err).__name__) from err
