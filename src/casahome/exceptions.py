"""Exception hierarchy for python-casahome."""

from __future__ import annotations


class CasaError(Exception):
    """Base class for all library errors."""


class CasaAuthError(CasaError):
    """Authentication failed or the refresh token is no longer valid."""


class CasaConnectionError(CasaError):
    """Network failure or timeout talking to Casa or Firebase."""


class CasaResponseError(CasaError):
    """Casa answered, but the body didn't match the expected schema.

    Usually means Casa changed a response shape. ``__cause__`` carries the
    underlying pydantic ValidationError.
    """


class CasaApiError(CasaError):
    """Casa returned a non-success response."""

    def __init__(
        self,
        status: int,
        code: str,
        display_title: str = "",
        display_message: str = "",
        request_id: str = "",
    ) -> None:
        self.status = status
        self.code = code
        self.display_title = display_title
        self.display_message = display_message
        self.request_id = request_id
        detail = display_message or display_title or code
        super().__init__(f"HTTP {status} [{code}] {detail}".strip())
