"""Unofficial async client for the Casa (getcasa.com) member API."""

from .api import CasaApi, is_unverified
from .auth import FirebaseAuth, TokenResponse
from .client import CasaClient
from .exceptions import (
    CasaApiError,
    CasaAuthError,
    CasaConnectionError,
    CasaError,
    CasaResponseError,
)

__version__ = "0.1.1"

__all__ = [
    "CasaApi",
    "CasaApiError",
    "CasaAuthError",
    "CasaClient",
    "CasaConnectionError",
    "CasaError",
    "CasaResponseError",
    "FirebaseAuth",
    "TokenResponse",
    "__version__",
    "is_unverified",
]
