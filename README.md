# python-casahome

Async Python client for the [Casa](https://getcasa.com) home membership API.

Unofficial. Not affiliated with or endorsed by Casa.

## Status

Version 0.3.0, alpha.
This source tree is local and unpublished. The PyPI package can be older.

- Most reads have been confirmed against live traffic.
- Version 0.3.0 adds writes whose method, path, request body and response were
  confirmed against live app traffic: moving inventory, Casa AI messages and
  ratings, request messages, plain-text to-do creation and deletion, to-do
  questions and hand-off, name-only entity model publishing, Autopilot,
  notification and access settings, mailbox claim, and document upload.
- A few older writes remain unverified. Treat them as experimental.
- Endpoint shapes were inferred from the iOS app and confirmed against live
  traffic where marked. Casa can change its private API at any time.

## Install

Install from PyPI:

```
pip install python-casahome
```

For this local source checkout:

```
uv sync --locked
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
| `todo_details` | yes | Question rounds and destination typed. Question items stay JSON. |
| `document_types` | yes | |
| `documents` | yes | App sends `limit=30&sort=uploaded`. `q` and `document_type` untested. |
| `document_details` | yes | |
| `document_thumbnail` | yes | Signed preview URLs. Never fetched by the library. |
| `document_file_metadata` | yes | Signed file URL and integer expiry only. No download. |
| `document_suggestions` | yes | Populated suggestions and citations. `view=all` observed. Other values and filtering semantics unverified. Matches empty, cursor null. |
| `document_structure_suggestions` | yes | Populated entity/definition IDs, labels, values, response times and citations. |
| `request_details` | yes | |
| `request_purchases` | partial | Envelope seen. Item lists empty. |
| `membership_info` | yes | Active membership. A home without one returns 404. |
| `help_center_bundle` | yes | Only `member_ios` tested. |
| `release_notes` | yes | |
| `release_notes_diff` | yes | |
| `casa_ai_bootstrap` | partial | Messages not seen populated. |
| `casa_ai_messages` | partial | |
| `requests_tab` | yes | Request cards seen populated. Task cards untested. |
| `completed_requests` | partial | |
| `calendar` | partial | Bounds sent as epoch seconds. |
| `calendar_busy` | partial | |
| `calendar_sync` | partial | |
| `mailbox`, `mail_items`, `packages` | partial | |
| `work_document_source` | partial | Only the `todo_id` selector tested. |
| `vehicles` | partial | |
| `utilities_insights` | partial | |
| `purchases` | partial | |
| `property_taxes` | partial | |
| `recurring_vendor_categories` | yes | |
| `recurring_vendors` | partial | |
| `bookable_handyman_tasks` | partial | Items stay opaque JSON. |
| `referral_code` | partial | `display` and `referred_homes` stay opaque JSON. |
| `membership_savings` | no | Returns 404 even with an active membership. |
| `availability_request_details` | no | |
| `task_details` | no | |
| `vendor_visit_details` | no | |
| `vendor_visit_autopilot_plan` | no | |
| `vendor_visit_calls` | no | |
| `vendor_visit_conversation` | no | |
| `vendor_visit_purchases` | no | |
| `casa_ai_events` | partial | Opt-in SSE stream. Transport, cursor replay and `message.upsert` updates confirmed. `resync_required` untested. |

### Writes

"Yes" means the method, path, request body and response were seen in live app
traffic and the library sends the same body.

| Method | Live-confirmed | Notes |
|---|---|---|
| `move_entity_to_room` | yes | Replaces the item's room. |
| `save_and_publish_entity`, `update_entity_model` | yes | Only `model.name` and empty `props`. No make or model-ID variants. |
| `send_ai_message` | yes | Sends an `Idempotency-Key` and returns it. Reply arrives on the event stream. |
| `rate_ai_message` | yes | `good` or `bad`. |
| `answer_todo_question` | yes | Answers seen. The skip body is unverified. |
| `submit_todo_question_round` | yes | |
| `respond_to_suggested_todo` | yes | Only `accept` seen. |
| `materialize_todo`, `send_todo_to_concierge` | yes | Only the `concierge` destination seen. |
| `create_todo_result`, `create_todo` | yes | Plain text only. Attachments and support-confirmation true unverified. |
| `delete_todo` | yes | Bodyless DELETE, HTTP 204. |
| `send_request_message` | yes | Member role and text, HTTP 201 message envelope. Attachments unverified. |
| `respond_to_document_structure_suggestion` | yes | Only `accepted`. Requires explicit `expected_values`. HTTP 200 with `saved: true`. |
| `update_autopilot_plan` | yes | |
| `update_notification_settings` | yes | Only the `push` channel seen. |
| `update_access_preferences` | yes | All four keys always sent. |
| `claim_mailbox` | yes | |
| `create_document_upload_sessions` | yes | Upload step 1. |
| `upload_document_content` | yes | Upload step 2, to Cloud Storage. |
| `create_document` | yes | Upload step 3. |
| `upload_document` | yes | All three steps, after checking the file against `document_types`. |
| `clear_ai_message_rating` | no | Path from the app only. |
| `update_entity_properties` | no | |

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

Live-confirmed writes are listed in the coverage table above. The remaining
writes were inferred from the app and haven't been exercised against the live
backend. Nothing is sent until you await a write method.

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
- Where the app sends an explicit `null` (for example `other_text` in to-do
  answers, or the access preference keys), the library sends `null` too.
- `send_ai_message` is the only write with an `Idempotency-Key`. Pass the
  returned key back to resend after a timeout without creating a duplicate.
- `send_request_message` only allows the `member` sender role.
- `create_todo_result` returns the full envelope, including
  `needs_support_confirmation`. `create_todo` is the older helper that returns
  just the todo.
- `save_and_publish_entity` requires `SaveAndPublishEntityRequest` with
  `model=EntityModelName(name=...)` and `props=[]`. The simpler
  `update_entity_model(home_id, entity_id, model_name)` sends that same body.
  Both return `SaveAndPublishEntityResponse`, including make, model and identity.
  Nonempty props, make selection and model-ID inputs aren't supported here.
  Empty-name and clear semantics remain unverified. The older property PATCH
  is still unverified.
- `document_suggestions(..., view=None)` omits the query by default. Supplied
  view strings are forwarded unchanged as query values. `view="all"` was
  observed. Other values and filtering semantics aren't verified.
  A null `next_cursor` was observed,
  but no cursor input is added without an observed query contract.
- `respond_to_document_structure_suggestion(home_id, document_id, suggestion_id,
  expected_values, decision="accepted")` sends only the confirmed response body.
  `expected_values` is required. Pass the suggestion's `current_values`, including
  an explicit empty list when appropriate. There isn't a default race guard or
  automatic refresh. Server mismatch handling remains unverified.
  `"accept"` and dismissal decisions are rejected. `SavedResponse.saved` requires
  a strict Boolean. No document PATCH is added.

### Document upload

```python
result = await api.upload_document(home_id, Path("inspection.pdf"), "inspection.pdf")
print(result.document.id, result.already_exists)
```

`upload_document` reads `document_types` first and rejects files whose MIME
type isn't allowed or whose size exceeds `max_file_size_bytes`. It then
reserves an upload session, sends the bytes to the signed Cloud Storage URL
Casa returns, and registers the document. The bytes go out in one request, so
the file is held in memory. The storage request carries no Casa credentials and
is only sent to `https://storage.googleapis.com`. Signed URLs never appear in
exception messages.

## CasaAI event stream

`api.casa_ai_events(home_id, after=None)` is an opt-in async generator over the
CasaAI server-sent event stream. It doesn't reconnect on its own. Close it with
`contextlib.aclosing` if you stop early:

```python
from contextlib import aclosing

from casahome.models import CasaAIMessageUpsertChange
from casahome.streaming import CasaAIResyncRequiredEvent, CasaAIThreadUpdateEvent

async with aclosing(api.casa_ai_events(home_id, after=saved_cursor)) as events:
    async for event in events:
        saved_cursor = event.id
        if isinstance(event, CasaAIResyncRequiredEvent):
            break  # Reload state, then subscribe again.
        if isinstance(event, CasaAIThreadUpdateEvent):
            for change in event.update().changes:
                if isinstance(change, CasaAIMessageUpsertChange):
                    print(change.message.sender_role, change.message.content)
```

`event.update()` parses the payload. `message.upsert` changes are typed, and
any other change type parses as `CasaAIUnknownChange` with its fields kept.
`event.payload` stays available as raw JSON.

Cursors (`event.id`, and `event_cursor` from `casa_ai_bootstrap`) are opaque.
Store them and pass them back unchanged. Resuming from an earlier cursor
replays the updates since that point.

Lines are capped at 64 KiB and events at 256 KiB. A 401 refreshes the token and
retries the GET once.

## Development

```
uv sync
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
```

Tests use synthetic data and a loopback test server. They make no live service
calls and need no credentials.

## License

MIT. See `LICENSE`.
