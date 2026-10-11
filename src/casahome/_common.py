"""Helpers shared by the read and write API modules.

Kept separate from ``api`` so the write mixin can use them without a circular
import. Nothing here does I/O.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from casahome.exceptions import CasaRequestError, CasaResponseError

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
M = TypeVar("M", bound=BaseModel)

_UNVERIFIED_NOTE = (
    "UNVERIFIED: path and HTTP method inferred statically from the iOS app (LIKELY). "
    "Not yet observed live."
)


def _parse(model: type[M], data: Any) -> M:
    """Validate a response, turning schema drift into a library error."""
    try:
        return model.model_validate(data)
    except ValidationError as err:
        message = f"Unexpected {model.__name__} response: {err.error_count()} validation error(s)"
    # Raise outside the handler. Pydantic's exception can contain private field
    # values, and even an implicit context would leak them in tracebacks.
    raise CasaResponseError(message)


def unverified(func: F) -> F:
    """Mark a method whose path or HTTP method hasn't been seen in real traffic."""
    func.__casa_unverified__ = True  # type: ignore[attr-defined]
    func.__doc__ = f"{_UNVERIFIED_NOTE}\n\n{func.__doc__ or ''}".rstrip()
    return func


def is_unverified(method: Callable[..., Any]) -> bool:
    return bool(getattr(method, "__casa_unverified__", False))


def _home(home_id: str) -> str:
    """Base for most per-home endpoints."""
    return f"/protected/home/{home_id}"


def _member_home(home_id: str) -> str:
    """Base for inventory, entity, room, and story endpoints only."""
    return f"/protected/member/home/{home_id}"


def _safe_id(value: str | int) -> str:
    """Validate new identifier inputs without assuming UUID or normalizing IDs."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("identifier must be a string or integer")
    text = str(value)
    if len(text) > 2048:
        raise ValueError("identifier exceeds SDK limit of 2048 characters")
    if text in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._~-]+", text):
        raise ValueError("identifier must be a nonempty safe path segment")
    return text


def _safe_home(home_id: str, *, member: bool = False) -> str:
    home_id = _safe_id(home_id)
    return _member_home(home_id) if member else _home(home_id)


def _write_id(value: str | int) -> str:
    """``_safe_id`` for writes, raising the scrubbed ``CasaRequestError``.

    ``_safe_id`` messages never include the rejected value. The original
    exception is dropped so no traceback context carries it either.
    """
    try:
        return _safe_id(value)
    except ValueError as err:
        message = str(err)
    raise CasaRequestError(message)


def _write_home(home_id: str, *, member: bool = False) -> str:
    home_id = _write_id(home_id)
    return _member_home(home_id) if member else _home(home_id)


def _positive_int(value: int, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return str(value)
