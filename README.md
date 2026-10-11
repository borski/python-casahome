# python-casahome

Async Python client for the [Casa](https://getcasa.com) home membership API.

Unofficial. Not affiliated with or endorsed by Casa.

## Status

Version 0.2.0, alpha.

- The library is read-heavy. Most methods are GETs, and most of those have been
  confirmed against live traffic.
- A few write methods exist. They are unverified and haven't been exercised
  against the real backend. Treat them as experimental.
- Endpoint shapes were inferred from the iOS app and confirmed against live
  traffic where marked. Casa can change its private API at any time.

## Install

Install from PyPI:

```
pip install python-casahome
```

Alternatively, install from the tagged GitHub source:

```
pip install "python-casahome @ git+https://github.com/borski/python-casahome@v0.2.0"
```

Requires Python 3.11 or newer.

## Authentication

Casa signs members in with Firebase phone auth, and SMS sign-in only works from
the real app. This library starts from a Firebase refresh token instead and
exchanges it for short-lived ID tokens.

Casa offers no official way to export that token. You obtain your own refresh
token from your own Casa app session, for example by inspecting your own app's
traffic during login and reading `refreshToken` from the Firebase token
response.

Treat the refresh token like a password. Anyone holding it can act as you.
Keep it in a password manager or secret store, never in source control.

The token doesn't expire on a timer, but Firebase can rotate it. Pass
`on_refresh_token_rotated` to `FirebaseAuth` (sync or async) and persist the new
value when it fires.

## Quick start

```python
import asyncio

from casahome import CasaApi


async def main() -> None:
    async with CasaApi.create("YOUR_REFRESH_TOKEN") as api:
        me = await api.bootstrap()
        for home in me.homes:
            print(home.display_address, home.status)
            weather = await api.weather(home.id)
            print(weather)


asyncio.run(main())
```

If you already own an `aiohttp.ClientSession` (for example in Home Assistant),
build the pieces yourself:

```python
from casahome import CasaApi, CasaClient, FirebaseAuth

auth = FirebaseAuth(session, refresh_token, on_refresh_token_rotated=save_token)
api = CasaApi(
    CasaClient(session, auth),
    device_id=stored_device_id,
    timezone="America/Los_Angeles",
)
```

`bootstrap` registers a device with Casa. Long-lived callers should persist
`api.device_id` and pass it back on the next start. Otherwise every restart adds
a new device to the account.

A runnable example lives in `examples/bootstrap.py`:

```
CASA_REFRESH_TOKEN=... uv run examples/bootstrap.py
```

## Coverage

Each method's docstring starts with `VERIFIED` or `UNVERIFIED`.
`casahome.is_unverified(api.some_method)` reports the same thing at runtime.

The "Live-confirmed" column means:

- **yes**: the path, method, response envelope and list item shapes were seen
  in live traffic.
- **partial**: the path, method and envelope were seen, but lists came back
  empty or items are kept as opaque JSON. Item models are inferred.
- **no**: inferred from the app only. Not seen working live.

The envelope is the top-level response keys. Item shape is the structure of
elements inside lists. All live confirmation dates from 2026-10.

### Reads

| Method | Live-confirmed | Notes |
|---|---|---|
| `bootstrap` | yes | Profile, homes, badge counts, app update info. |
| `onboarding_details` | yes | Raw dict, or `None` on 304. |
| `onboarding_details_typed` | yes | Typed version of the above. |
| `onboarding_availability` | yes | |
| `home_details` | yes | Stories, rooms, inventory entities. |
| `inventory_item` | yes | One entity. |
| `inventory_makes` | yes | |
| `inventory_enums` | yes | Takes a property's `enum_type` key, such as `light_fixture_type`. |
| `inventory_paint_matches` | yes | |
| `inventory_service_history` | partial | Room and home targets seen. Entity target untested. |
| `room_types` | yes | |
| `room_image_options` | yes | |
| `room_image_candidates` | yes | |
| `matterport_images` | yes | |
| `badge_counts` | yes | |
| `weather` | yes | |
| `credits_summary` | yes | |
| `home_feed` | yes | `props` varies by card template and stays a JSON dict. |
| `home_members` | yes | |
| `schedule_preferences` | yes | |
| `notification_settings` | yes | |
| `access_preferences` | partial | Option values not seen populated. |
| `autopilot_plans` | yes | |
| `paint_brands`, `paint_collections`, `paint_colors`, `paint_search` | yes | |
| `suggested_todos` | yes | Question rounds and destination stay opaque. |
| `todo_details` | yes | Same caveat. |
| `document_types` | yes | |
| `help_center_bundle` | yes | Only `member_ios` tested. |
| `release_notes` | yes | |
| `release_notes_diff` | yes | |
| `casa_ai_bootstrap` | partial | Messages not seen populated. |
| `casa_ai_messages` | partial | |
| `requests_tab` | partial | |
| `completed_requests` | partial | |
| `calendar` | partial | Bounds sent as epoch seconds. |
| `calendar_busy` | partial | |
| `calendar_sync` | partial | |
| `mailbox`, `mail_items`, `packages` | partial | |
| `documents` | partial | Query parameters untested. |
| `work_document_source` | partial | Only the `todo_id` selector tested. |
| `vehicles` | partial | |
| `utilities_insights` | partial | |
| `purchases` | partial | |
| `property_taxes` | partial | |
| `recurring_vendor_categories` | yes | |
| `recurring_vendors` | partial | |
| `bookable_handyman_tasks` | partial | Items stay opaque JSON. |
| `referral_code` | partial | `display` and `referred_homes` stay opaque JSON. |
| `request_details` | no | |
| `membership_info` | no | Returned 404 in testing. |
| `membership_savings` | no | Returned 404 in testing. |
| `availability_request_details` | no | |
| `document_details` | no | |
| `document_suggestions` | no | |
| `document_structure_suggestions` | no | |
| `request_purchases` | no | |
| `task_details` | no | |
| `vendor_visit_details` | no | |
| `vendor_visit_autopilot_plan` | no | |
| `vendor_visit_calls` | no | |
| `vendor_visit_conversation` | no | |
| `vendor_visit_purchases` | no | |
| `casa_ai_events` | partial | Opt-in SSE stream. Transport confirmed, event payloads untested. |

### Writes

| Method | Live-confirmed |
|---|---|
| `create_todo_result` | no |
| `create_todo` | no |
| `send_request_message` | no |
| `update_entity_properties` | no |

## Models

Import models from `casahome.models`. Unknown response fields are kept in
`model_extra` rather than dropped, so new server fields don't break parsing.
A response that doesn't match the expected shape raises `CasaResponseError`.

Identifier arguments are checked before any request. They must be nonempty
path-safe segments (letters, digits, `.`, `_`, `~`, `-`). IDs aren't trimmed,
lowercased or forced to UUIDs.

Responses can contain personal data: names, contact details, messages,
documents and purchase info. Avoid logging whole models. URLs in responses are
returned as data. The library never follows them.

## Writes

The write methods are unverified. Their request bodies were inferred from the
app and have not been exercised against the live backend. Nothing is sent until
you await a write method.

- Each write is sent exactly once. There is no retry, including on 401. The ID
  token is refreshed before the request, and a 401 raises `CasaAuthError`.
  Deciding whether to repeat is up to you.
- If the response fails to parse, the server may still have performed the
  action. Don't assume a parse error means it's safe to repeat.
- Request bodies are strict Pydantic models. Unknown fields and invalid values
  raise `CasaRequestError` before any I/O. Free-text fields are capped at
  10,000 characters.
- Optional fields set to `None` are omitted from the JSON. Empty strings and
  empty lists are sent as given.
- `send_request_message` only allows the `member` sender role.
- `create_todo_result` returns the full envelope, including
  `needs_support_confirmation`. `create_todo` is the older helper that returns
  just the todo.

## CasaAI event stream

`api.casa_ai_events(home_id, after=None)` is an opt-in async generator over the
CasaAI server-sent event stream. It doesn't reconnect on its own. Close it with
`contextlib.aclosing` if you stop early:

```python
from contextlib import aclosing

from casahome.streaming import CasaAIResyncRequiredEvent, CasaAIThreadUpdateEvent

async with aclosing(api.casa_ai_events(home_id, after=saved_cursor)) as events:
    async for event in events:
        saved_cursor = event.id
        if isinstance(event, CasaAIResyncRequiredEvent):
            break  # Reload state, then subscribe again.
        if isinstance(event, CasaAIThreadUpdateEvent):
            update = event.payload  # Opaque JSON.
```

Lines are capped at 64 KiB and events at 256 KiB. A 401 refreshes the token and
retries the GET once.

## Development

```
uv sync
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

Tests use synthetic data and a loopback test server. They make no network calls
and need no credentials.

## License

MIT. See `LICENSE`.
