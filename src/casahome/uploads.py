"""Upload bytes to a Casa-issued Cloud Storage resumable session URL.

This is the only request the library sends to a host other than Casa. It goes
out without Casa credentials and only to the expected storage origin. The
signed session URL is a credential in its own right, so it never appears in
logs or exception messages.
"""

from __future__ import annotations

import aiohttp
from yarl import URL

from .exceptions import CasaApiError, CasaConnectionError, CasaRequestError

STORAGE_UPLOAD_SCHEME = "https"
STORAGE_UPLOAD_HOST = "storage.googleapis.com"
STORAGE_UPLOAD_PORT = 443
SINGLE_REQUEST_UPLOAD_NOTE = (
    "The whole file is sent as the single, final chunk of the resumable session, "
    "so it's held in memory. Casa's max_file_size_bytes bounds the size."
)


def validate_storage_url(session_url: str) -> URL:
    """Accept only ``https://storage.googleapis.com/...`` with no credentials."""
    if not isinstance(session_url, str) or len(session_url) > 8192:
        raise CasaRequestError("upload session URL must be a string under 8192 characters")
    try:
        url = URL(session_url, encoded=True)
    except ValueError:
        message = "upload session URL is malformed"
    else:
        if (
            url.scheme == STORAGE_UPLOAD_SCHEME
            and url.host == STORAGE_UPLOAD_HOST
            and url.port == STORAGE_UPLOAD_PORT
            and url.user is None
            and url.password is None
        ):
            return url
        message = "upload session URL must be an https Cloud Storage URL"
    # Never echo the URL. It carries a signed upload credential.
    raise CasaRequestError(message)


async def put_storage_bytes(
    session: aiohttp.ClientSession,
    session_url: str,
    data: bytes,
    mimetype: str,
    *,
    timeout: aiohttp.ClientTimeout,
) -> None:
    """PUT ``data`` as the complete content of a resumable upload session.

    Sends ``Content-Type``, ``Content-Length`` and ``Content-Range: bytes
    0-{n-1}/{n}``. No Authorization or Casa app headers. One attempt, no
    redirects. Any status other than 200/201 raises ``CasaApiError`` without
    the response body.

    ``session`` is retained for source compatibility but isn't used or closed.
    Storage owns a fresh session with no caller headers, auth, cookies,
    middleware or environment proxy/netrc configuration. Default TLS
    verification stays enabled. This session closes even on cancellation.
    """
    url = validate_storage_url(session_url)
    if not isinstance(data, bytes) or not data:
        raise CasaRequestError("upload data must be nonempty bytes")
    size = len(data)
    headers = {
        "Content-Type": mimetype,
        "Content-Length": str(size),
        "Content-Range": f"bytes 0-{size - 1}/{size}",
    }
    failure = ""
    try:
        async with (
            aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(), trust_env=False) as storage,
            storage.put(
                url,
                data=data,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
                raise_for_status=False,
            ) as response,
        ):
            status = response.status
    except TimeoutError:
        failure = "Storage upload timed out"
    except aiohttp.ClientError:
        failure = "Storage upload connection failed"
    if failure:
        # Raised outside the handler: aiohttp errors can include the signed URL.
        raise CasaConnectionError(failure)
    if status not in (200, 201):
        raise CasaApiError(status, "storage_upload_failed")
