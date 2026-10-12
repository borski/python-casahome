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

Casa signs members in with Firebase phone auth. This library doesn't implement
phone/SMS sign-in. An independent login flow would need Casa's app-verification
and callback requirements established first. The supported setup starts from a
Firebase refresh token and exchanges it for short-lived ID tokens.

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
| `rename_room` | yes | `PATCH` with `room_type_id` and `name`, both always sent. |
| `save_and_publish_entity`, `update_entity_make_model`, `update_entity_model` | partial | Observed publish subset includes `model.name` and empty `props`. Shared ID/name encoding is statically verified, not traffic verification of every variant. Model-ID traffic remains UNVERIFIED. No clear. |
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

### Offline reconstructed contracts

The following SDK methods are **UNVERIFIED against Casa's backend**. Their
request/response codecs were reconstructed from the compiled app. Synthetic
loopback tests check serialization and parsing only. No MCP or Home Assistant
tool is added by these SDK methods.

| Method | Route beneath the home prefix | Result |
|---|---|---|
| `update_request_detail` | `PATCH requests/{id}` | Direct six-field `UpdateRequestDetailResponse`. Optional title/read_state (`read` or `unread`) are omitted when absent. |
| `dismiss_document_structure_suggestion` | `POST documents/{id}/structure_suggestions/{id}/respond` | `SavedResponse`. Requires ordered caller-supplied `expected_values`, even when empty. The existing accepted-only method is unchanged. |
| `update_task`, `delete_task`, `transfer_task_to_concierge` | `PATCH/DELETE tasks/{id}`, `POST tasks/{id}/transfer_to_concierge` | TaskDetails (scalar edits only), BasicMessageResponse, direct TransferToConciergeResponse. DELETE and transfer have no body. |
| `delete_document` | `DELETE documents/{id}` | `HomeDocumentDeleteResponse.deleted`. False is retained on HTTP success. |
| `update_room_properties` | `PATCH room/{id}/props` under the **member** home prefix | Required props list of definition_id plus optional string value. No enum or clear input. |
| `update_story` | `PATCH story/{id}` under the **member** home prefix | Optional name/floor_number, BasicMessageResponse. |
| `retailer_discounts` | `GET retailer_discounts` | Required `data` array with typed scalar items and preserved unknown fields. Never follows URLs. |
| `create_support_request` | `POST support_requests` | Text-only, direct request_id. This may contact a person. No attachments. |
| `mark_vendor_visit_conversation_read` | `PATCH vendor_visits/{id}/conversation/read` | Bodyless, required `ok` Boolean. False isn't treated as success. |

Writes make a single attempt without 401 replay. A response parse failure after
a write is an unknown outcome, not proof the write didn't happen. No implicit
clearing, conflict retry, dispatch, booking or follow-up action is performed.
Resource refresh needs raw response bytes rather than the current JSON-only
client transport, so it isn't exposed. Mail detail, utility statements and
vendor message sends need further nested response proof. Shopping, billing and
credential operations remain excluded.

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
- `send_ai_message` is the only write with an `Idempotency-Key`. The returned
  key supports tracing, but server deduplication hasn't been tested. A failed
  send may have succeeded. Check the thread before considering another attempt.
- `send_request_message` only allows the `member` sender role.
- `create_todo_result` returns the full envelope, including
  `needs_support_confirmation`. `create_todo` is the older helper that returns
  just the todo.
- `save_and_publish_entity` takes a `SaveAndPublishEntityRequest` with
  optional `make` and `model`, each a `CatalogFieldId(id=...)` or
  `CatalogFieldName(name=...)`, and `props=[]`. At least one side is required.
  `update_entity_make_model(home_id, entity_id, *, make_id=, make_name=,
  model_id=, model_name=)` builds the same body: at most one of id or name per
  side, at least one side. `update_entity_model(home_id, entity_id, model_name)`
  is the model-name-only shortcut. All return `SaveAndPublishEntityResponse`,
  including optional make/model and required identity, entity_id and status.
  Missing or null make/model fields are accepted based on the compiled decoder,
  not a claim of observed server responses. Casa matches names against its catalog
  and may store a different canonical name. An unmatched name raises
  `CasaApiError` with status 400 and code `CATALOG_MODEL_UNVERIFIED`. Names
  are capped at 256 characters and can't be blank. Clearing a make or model
  isn't supported. The compiled clear case encodes explicit null, but its server
  semantics remain UNVERIFIED. SDK `None` omits a side and never clears it.
  Model-ID selection has static codec evidence only, not verified traffic.
  Nonempty props are
  rejected. The older property PATCH is still unverified.
- `rename_room(home_id, room_id, *, room_type_id, name)` sends both keys. Pass
  the room's current `room_type_id` (from `home_details`) to keep its type.
  Room creation isn't implemented.
- `CasaApiError` reads `display_title`, `display_message` and `request_id`
  from either camelCase or snake_case error bodies. Both are seen live.
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

### Additional reconstructed workflows

These methods are implemented with strict request models, typed responses and
offline tests. Unless explicitly noted, they remain `UNVERIFIED`. Static client
code doesn't establish current backend acceptance, business effects or safe retries.
None is automatically executed or exposed as a live MCP action.

| Methods | Request distinction and remaining uncertainty |
|---|---|
| `update_todo` | Optional title, brief, emoji and attachment deltas omit `None`. Clear behavior unknown. |
| `reject_suggested_todo` | `reject` with optional `dismissed` or `already_handled` reason. |
| `confirm_todo_support` | Caller-supplied strict Boolean, no inferred classification. |
| `update_document` | Date omitted, supplied string, or explicit null. Date format and clearing effects unverified. |
| `analyze_document`, `organize_document` | Analysis requires an explicit `reanalyze` Boolean. Organization has no JSON body. |
| `update_schedule_preferences` | Both day-number and time-window-ID arrays required. Numbering and replacement rules unknown. |
| `update_availability_slots` | Required integer windows. Time units and submission semantics unknown. |
| `reorder_todo_section` | Required revision and ordered IDs. No conflict refetch/retry. |
| `retry_todo` | Explicit bodyless preparation action, not transport retry. |
| `cancel_vendor_visit` | Bodyless PUT. Fees and side effects possible, not established. |
| `add_mailbox_recipient` | VERIFIED for first/last names. Business-name and partial-name variants unverified. |
| `update_mailbox_auto_archive` | VERIFIED for `30` and explicit null. Other values and disposal effects unverified. |
| `remove_mailbox_recipient` | Bodyless DELETE. Recipient restrictions and reversibility unknown. |
| `mark_mail_item_read`, `mark_mail_item_unread`, `set_mail_item_archived` | Bodyless POSTs. Archiving isn't a shredding claim. |
| `validate_package_tracking_number`, `add_tracked_package` | Validation uses POST. Package direction is explicit. |
| `update_package`, `requeue_package_pickup` | Update uses POST. `deleted` may remove a record, not merely cancel pickup. |
| `create_package_pickup_item` | Requires a matching typed image-upload receipt. No multipart-upload helper or time-slot selection. |
| `set_package_auto_archive` | Required nullable integer. Allowed ranges unknown. |
| `create_inventory_entity`, `create_inventory_lighting`, `create_paint_from_library` | Capture constructors. No guessed custom make/model tags or lighting-kind values. |

Document-date examples preserve the distinction between unchanged and clearing:

```python
from casahome.models import UpdateDocumentBody

rename_only = UpdateDocumentBody(name="Warranty")  # No document_date key.
set_date = UpdateDocumentBody(document_date="2020-01-01")  # Format is unverified.
clear_date = UpdateDocumentBody(document_date=None)  # Explicit JSON null.
```

Forwarding, shredding, check deposit, reservation submission and document-suggestion
dismissal aren't invented from endpoint names or nearby UI text. More evidence is needed.

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

Local paths are opened once and must refer to nonempty regular files. Symlinks
to regular files are allowed. FIFOs, devices and directories are rejected.
The actual read is capped at `max_file_size_bytes` plus one detection byte,
including when the file grows. The client's configured total timeout bounds
waiting for a file read. Cancellation can't interrupt a filesystem call already
running in the worker thread, which closes its descriptor when it finishes.

Storage uploads use a separate session with no caller Authorization, BasicAuth,
cookies, custom headers or middleware. Environment proxy/netrc settings aren't
used. Normal TLS verification stays enabled. The storage session closes on
success, failure or cancellation. The caller's Casa session stays open.

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
