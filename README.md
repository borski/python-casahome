# python-casahome

An async Python client for the [Casa](https://getcasa.com) member API. This is
an unofficial library, unaffiliated with Casa. It uses a private API that Casa
can change without notice.

The current source version is 0.3.1. The package is alpha software. Some calls
were observed in app traffic, while others were reconstructed from the app and
have never been checked against Casa's backend. The SDK doesn't cover the full
app or backend API. See the method docstrings for the evidence and limits of a
particular call.

## Install

```sh
pip install python-casahome
```

Python 3.11 or newer is required. To work from a source checkout, use
`uv sync --locked`.

## Authentication

Casa uses Firebase phone authentication. This library starts with a Firebase
refresh token and exchanges it for short lived ID tokens. It doesn't implement
phone or SMS sign in. There is no official Casa token export. If you inspect
your own app session to obtain a token, keep it out of logs and source control.
Treat it like a password.

Firebase can rotate refresh tokens. For a long lived client, construct
`FirebaseAuth` with `on_refresh_token_rotated` and store the new token when the
callback runs. The callback can be synchronous or asynchronous. Callback
failures are logged and don't fail the request, so verify that storage
succeeded.

## Quick start

```python
import asyncio

import aiohttp

from casahome import CasaApi, CasaClient, FirebaseAuth


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        auth = FirebaseAuth(
            session,
            "YOUR_REFRESH_TOKEN",
            on_refresh_token_rotated=save_token,
        )
        api = CasaApi(
            CasaClient(session, auth),
            device_id="YOUR_PERSISTED_DEVICE_ID",
        )
        me = await api.bootstrap()
        for home in me.homes:
            print(home.status)
            print(await api.weather(home.id))


asyncio.run(main())
```

Define `save_token` to write to your secret store and fail if the write doesn't
succeed. Replace `YOUR_PERSISTED_DEVICE_ID` with a stable value that you retain
between runs.

`bootstrap` registers a device. Persist `api.device_id` and pass it as
`device_id` on later starts. Otherwise each start registers a new device.
`CasaApi.create` is a convenience for short scripts, but it doesn't install a
token rotation callback. Use the explicit setup above when the token must
survive restarts.

If you own an `aiohttp.ClientSession`, you can reuse it:

```python
from casahome import CasaApi, CasaClient, FirebaseAuth

auth = FirebaseAuth(session, refresh_token, on_refresh_token_rotated=save_token)
api = CasaApi(CasaClient(session, auth), device_id=stored_device_id)
```

The caller owns that session and must close it. `CasaApi.create` owns and closes
its session instead. A runnable bootstrap example is in
`examples/bootstrap.py`. It doesn't persist a rotated token. Its `--show-token`
option prints the token to the terminal, so don't use it in captured logs. Set
`CASA_REFRESH_TOKEN` in your shell to run it:

```sh
uv run examples/bootstrap.py
```

## API coverage and evidence

Read methods include `home_details`, `inventory_item`, `weather`,
`credits_summary`, `requests_tab`, `request_details`, `todo_details`,
`documents`, `document_suggestions`, `autopilot_plans`, `mail_items`,
`packages` and `calendar`. Some routes were observed with populated items.
Others were observed only with empty lists, or have untested query variants.
For example, `document_suggestions` was observed with `view="all"` but other
filter values aren't confirmed. Several visit and task detail reads remain
unverified against the backend.

Observed write paths include `move_entity_to_room`, `rename_room`,
`send_ai_message`, `send_request_message`, `create_todo_result`, `delete_todo`,
`answer_todo_question`, `update_autopilot_plan`,
`update_notification_settings`, `update_access_preferences` and
`upload_document`. An observed path doesn't verify every optional input. For
example, `save_and_publish_entity` was observed with `model.name` and empty
`props`. The shared compiled codec supports ID and name selections, but
model ID traffic hasn't been verified. The SDK doesn't expose clearing make or
model. The app's compiled clear case encodes JSON null, but backend clearing
behavior is unknown.

Methods marked `UNVERIFIED` are based on static app reconstruction and local
synthetic tests, not a successful backend call. They include
`update_document`, `update_schedule_preferences`, `update_availability_slots`,
`cancel_vendor_visit`, `update_entity_properties` and the newer
`update_request_detail`, `dismiss_document_structure_suggestion`,
`update_task`, `delete_task`, `transfer_task_to_concierge`, `delete_document`,
`update_room_properties`, `update_story`, `retailer_discounts`,
`create_support_request` and `mark_vendor_visit_conversation_read`.
`update_document` is a PATCH method, with unverified date and clearing effects.
`create_support_request` may contact a person. A message, `ok` or `deleted`
field in a response must be read as returned. HTTP success alone doesn't
establish the action's business effect.

Use `casahome.is_unverified(api.update_document)` to check a method's marker.
Read its docstring for finer distinctions. An unmarked method can still have
untested variants. Response models live in `casahome.models`. They keep unknown
fields in `model_extra` and distinguish response envelopes from their nested
items. A schema mismatch raises `CasaResponseError`.

This SDK is separate from any MCP or Home Assistant adapter. A library method
doesn't imply that an adapter exposes it. Adapters choose their own limited
tools and action gates.

## Write behavior

Each ordinary Casa mutation is sent once. The client force refreshes the ID
token before sending it and doesn't replay the mutation after a 401. Normal GET
requests retry once after a 401. `bootstrap` is a deliberate exception: it is a
POST that registers a device and keeps the one time 401 retry. `upload_document`
is a multi step workflow with a policy GET and three write steps. Each step is
attempted once, and its Cloud Storage PUT uses no Casa token. A response parsing
failure, timeout or connection error after a mutation can leave its outcome
unknown. Check the resulting state before deciding whether to send another
request. The `Idempotency-Key` on `send_ai_message` helps trace a send, but
server deduplication hasn't been verified.

Write bodies use strict validation. Invalid or unknown input fields raise
`CasaRequestError` before the write. Optional `None` values generally omit a
field, while empty strings and lists are sent as supplied. Some contracts send
explicit null, including the access preference fields. In
`UpdateDocumentBody`, omitting `document_date` leaves the key out, and
explicit `document_date=None` sends null. Don't treat those forms as
interchangeable. The backend effect of document date clearing is unverified.

Path identifiers must be nonempty safe segments. They aren't normalized to
UUIDs. Responses can contain home addresses, coordinates, phone numbers, email
addresses, account identifiers, payment and membership metadata, private
messages, documents, purchase details and short lived signed URLs. Avoid
logging complete models, request paths, event payloads or read exceptions.
Response URLs aren't followed unless a documented workflow requires it.
`upload_document` follows only its validated Cloud Storage session URL.

## Document upload

```python
from pathlib import Path

result = await api.upload_document(home_id, Path("inspection.pdf"), "inspection.pdf")
print(result.document.id, result.already_exists)
```

`upload_document` first reads `document_types` to check MIME type and file
size. It reserves a session, uploads the bytes to the signed Cloud Storage URL
Casa returns, then registers the document. `find_todos=True` asks Casa to look
for suggested tasks. Each step is attempted once. An error in a later step
doesn't undo an earlier one.

`source` can be bytes or a local path. The MIME type is guessed from `filename`
when omitted and must appear in Casa's allowed MIME types. Local paths must
open as nonempty regular files. Symlinks to regular files are allowed. The read
is bounded by Casa's reported file size limit, plus one byte for detecting an
oversized file. The entire file is held in memory for one storage request. The
client timeout bounds the file read and storage request, but cancellation can't
stop a filesystem call already running in a worker thread.

The filename must contain 1 to 1,024 characters, include a nonwhitespace
character and contain no controls. The signed URL can contain at most 8,192
characters, must contain no embedded credentials and must use HTTPS on
`storage.googleapis.com` at port 443. A separate storage session sends no Casa
credentials, caller headers, cookies, environment proxy settings or netrc
configuration. It doesn't follow redirects and accepts only HTTP 200 or 201.
Keep signed session URLs private. See the `upload_document` and
`upload_document_content` docstrings for the complete contract.

## Casa AI events

`casa_ai_events` is an opt in server sent event stream. A live connection and
some update traffic were observed, but the full event and reconnect behavior
isn't verified. The generator doesn't reconnect automatically. Close it when
you stop reading early:

```python
from contextlib import aclosing

from casahome.models import CasaAIMessageUpsertChange
from casahome.streaming import CasaAIResyncRequiredEvent, CasaAIThreadUpdateEvent

async with aclosing(api.casa_ai_events(home_id, after=saved_cursor)) as events:
    async for event in events:
        if event.id is not None:
            saved_cursor = event.id
        if isinstance(event, CasaAIResyncRequiredEvent):
            break  # Reload state before subscribing again.
        if isinstance(event, CasaAIThreadUpdateEvent):
            for change in event.update().changes:
                if isinstance(change, CasaAIMessageUpsertChange):
                    print(change.message.sender_role, change.message.content)
```

An `after` cursor is opaque. Store it unchanged. `event.update()` validates the
decoded thread update. `event.payload` retains the decoded JSON value, while
`event.data` retains the original event text. Other change types remain
available as `CasaAIUnknownChange`. The stream limits lines to 64 KiB, events to
256 KiB and cursors to 2,048 characters without controls. The cursor is sent as
both `after` and `Last-Event-ID`. Redirects are disabled. A 60 second socket
read gap raises a connection error. HTTP 204 ends the generator, and incomplete
event framing at EOF is discarded. `resync_required` is yielded once before
the response closes. The GET can refresh an expired token and retry once on
401. That retry behavior doesn't apply to ordinary mutations.

## Development

```sh
uv sync
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
```

Tests use synthetic data and a loopback server. They don't call Casa or need
credentials.

## License

MIT. See `LICENSE`.
