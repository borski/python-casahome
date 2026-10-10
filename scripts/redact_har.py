"""Build redacted test fixtures from a Casa HAR capture.

Usage:
    uv run scripts/redact_har.py /path/to/capture.har

Writes tests/fixtures/bootstrap.json and onboarding_details.json. Every key is
kept, every value that could identify a person, a home, or grant access is
replaced with an obviously fake value of the same type.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SIGNED_URL_RE = re.compile(r"\?(?=[^\"]*(sig=|X-Amz-|token=|Signature=|Expires=))[^\"\s]*")

FAKE_STRINGS = {
    "email": "member@example.com",
    "first_name": "Test",
    "last_name": "Member",
    "phone_number": "+15550000000",
    "address_street_number": "123",
    "address_street": "Example St",
    "address_subpremise": None,
    "address_city": "Springfield",
    "address_state": "CA",
    "address_postal_code": "00000",
    "payment_description": "Card ending 0000",
    "payment_method_last4": "0000",
    "payment_method_brand": "visa",
    "matterport_model_id": "FAKEMODEL00",
    "matterport_model_password": "REDACTED",
    "calendar_sync_email": None,
    "home_image_url_cache_key": "REDACTED",
    "avatar_url_cache_key": None,
}
FAKE_NUMBERS: dict[str, float] = {"latitude": 37.0, "longitude": -122.0, "card_surcharge_rate": 0.0}
SECRET_SUFFIXES = ("_password", "_token", "_secret")
SAFE_URL_PREFIXES = ("https://apps.apple.com/",)
AGREEMENT_PLACEHOLDER = "Agreement text redacted for fixture size."


class Redactor:
    def __init__(self) -> None:
        self._uuids: dict[str, str] = {}

    def fake_uuid(self, real: str) -> str:
        key = real.lower()
        if key not in self._uuids:
            n = len(self._uuids) + 1
            self._uuids[key] = f"00000000-0000-4000-8000-{n:012d}"
        return self._uuids[key]

    def scrub_string(self, value: str) -> str:
        value = UUID_RE.sub(lambda m: self.fake_uuid(m.group(0)), value)
        return SIGNED_URL_RE.sub("?REDACTED", value)

    def walk(self, obj: Any, key: str | None = None, parent_key: str | None = None) -> Any:
        if isinstance(obj, dict):
            return {k: self.walk(v, k, key) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.walk(v, key, parent_key) for v in obj]
        if key in FAKE_STRINGS:
            return FAKE_STRINGS[key] if obj is not None else None
        if key in FAKE_NUMBERS and isinstance(obj, (int, float)):
            return FAKE_NUMBERS[key]
        if key and key.endswith(SECRET_SUFFIXES) and isinstance(obj, str):
            return "REDACTED"
        if parent_key == "pending_agreements" and key == "content" and isinstance(obj, str):
            return AGREEMENT_PLACEHOLDER
        if key and ("amount" in key) and isinstance(obj, (int, float)):
            return 0
        if (
            key
            and key.endswith("_url")
            and isinstance(obj, str)
            and not obj.startswith(SAFE_URL_PREFIXES)
        ):
            return "https://example.com/redacted.jpg"
        if isinstance(obj, str):
            return self.scrub_string(obj)
        return obj


def _body(entry: dict[str, Any]) -> Any:
    content = entry["response"].get("content", {})
    text = content.get("text")
    if not text:
        return None
    raw: bytes = base64.b64decode(text) if content.get("encoding") == "base64" else text.encode()
    with contextlib.suppress(OSError):
        raw = gzip.decompress(raw)
    return json.loads(raw)


def main(har_path: str) -> None:
    har = json.loads(Path(har_path).read_text())
    redactor = Redactor()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    wrote = []
    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        if url.endswith("/protected/member/bootstrap"):
            data = redactor.walk(_body(entry))
            (FIXTURES / "bootstrap.json").write_text(json.dumps(data, indent=2) + "\n")
            wrote.append("bootstrap.json")
        elif url.endswith("/onboarding/details"):
            meta = {
                "status": entry["response"]["status"],
                "note": "Captured as 304 Not Modified. No body available.",
                "body": redactor.walk(_body(entry)),
            }
            (FIXTURES / "onboarding_details.json").write_text(json.dumps(meta, indent=2) + "\n")
            wrote.append("onboarding_details.json")
    print("wrote:", ", ".join(wrote) or "nothing")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
