# python-casahome

Unofficial async Python client for the [Casa](https://getcasa.com) member API. Built from observed app traffic and static analysis of the iOS app. Not affiliated with or endorsed by Casa.

## Install

```
uv pip install -e .
```

Once published: `uv add python-casahome`.

## Getting a refresh token

Casa signs members in with Firebase Phone Auth. SMS sign-in requires the real app (Firebase verifies it via APNs), so this library starts from a Firebase refresh token. Capture one by proxying the iOS or Mac app (Proxyman, Charles, mitmproxy) during login and grabbing `refreshToken` from the `verifyPhoneNumber` or `securetoken` response. Store it in a password manager. It doesn't expire on a timer, but Firebase may rotate it. Read `auth.refresh_token` after use and persist the new value.

## Usage

```python
import asyncio
from casahome import CasaApi


async def main() -> None:
    async with CasaApi.create("YOUR_REFRESH_TOKEN") as api:
        me = await api.bootstrap()
        for home in me.homes:
            print(home.display_address, home.status)


asyncio.run(main())
```

In Home Assistant or anywhere you already own an `aiohttp.ClientSession`, build the pieces yourself:

```python
auth = FirebaseAuth(session, refresh_token, on_refresh_token_rotated=save_token)
api = CasaApi(CasaClient(session, auth), device_id=stored_device_id, timezone="America/Los_Angeles")
```

`bootstrap` registers a device with Casa. Long-lived callers should persist `api.device_id` and pass it back on the next start, or every restart adds a new phantom device to the account. Firebase may rotate the refresh token. `on_refresh_token_rotated` (sync or async) gets the new one so you can save it.

Runnable example:

```
CASA_REFRESH_TOKEN=... uv run examples/bootstrap.py
```

With 1Password (token lives in the vault, never on disk), put a secret reference in a gitignored `.env`:

```
CASA_REFRESH_TOKEN=op://<vault>/<item>/<field>
```

Then:

```
op run --env-file=.env -- uv run examples/bootstrap.py
```

## Confidence

| Label | Meaning |
|-------|---------|
| VERIFIED | Seen in real traffic. Path, method, and body known. |
| UNVERIFIED | Path, HTTP method, and schema recovered from the app binary by disassembly (method confidence LIKELY: the method accessor and path are built in the same function). Query params and response wrappers are still partly inferred. Not yet seen in live traffic. |

`casahome.is_unverified(api.some_method)` tells you at runtime.

| Method | Status |
|--------|--------|
| `bootstrap` | VERIFIED |
| `onboarding_details` | VERIFIED |
| `home_details` | UNVERIFIED |
| `badge_counts` | UNVERIFIED |
| `weather` | UNVERIFIED |
| `requests_tab` | UNVERIFIED |
| `request_details` | UNVERIFIED |
| `calendar` | UNVERIFIED |
| `credits_summary` | UNVERIFIED |
| `mailbox` | UNVERIFIED |
| `mail_items` | UNVERIFIED |
| `packages` | UNVERIFIED |
| `create_todo` | UNVERIFIED, write |

Billing, membership, payments, and agreements are out of scope on purpose.

## Development

```
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest
```

Tests never touch the network. Fixtures are redacted from a real capture by `scripts/redact_har.py`.
