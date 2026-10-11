"""Strict write codecs with per-variant evidence recorded on API methods.

Plain-text todo creation and member request messages were observed in traffic.
Attachments and property PATCH contracts remain static and UNVERIFIED.
These models neither authorize nor execute operations.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError

from casahome.exceptions import CasaRequestError
from casahome.models._base import CasaModel
from casahome.models.requests import RequestMessage
from casahome.models.todos import AttachMediaPayload as LegacyAttachMediaPayload
from casahome.models.todos import CreateTodoBody as LegacyCreateTodoBody
from casahome.models.todos import TodoDetail

WRITE_TEXT_MAX_CHARS = 10_000
"""Cap on free-text write fields (to-do content, message content, property values).

Not a server limit, which is UNKNOWN. It bounds what a caller, or an agent
driving one, can send in a single write. Real to-dos and messages are short.
"""

_WriteText = Annotated[str, Field(max_length=WRITE_TEXT_MAX_CHARS)]

_WRITE_CONFIG = ConfigDict(
    extra="forbid", strict=True, validate_assignment=True, revalidate_instances="always"
)


class _WriteModel(BaseModel):
    """Reject coercion and unknown write fields, including nested fields."""

    model_config = _WRITE_CONFIG


class AttachMediaPayload(LegacyAttachMediaPayload):
    """Existing upload IDs only. No upload, URL fetch or lifecycle inference.

    The recovered codec always encodes upload_ids, including an empty list.
    This strict public companion requires callers to supply that list explicitly.
    """

    model_config = _WRITE_CONFIG
    upload_ids: list[str] = Field(...)


class CreateTodoBody(LegacyCreateTodoBody):
    """Strict public companion to the legacy todo body, with the same wire keys."""

    model_config = _WRITE_CONFIG
    content: _WriteText
    attachments: AttachMediaPayload | None = None


class CreateTodoResponse(CasaModel):
    """Required app envelope. A missing flag must never become false.

    TodoDetail is the existing model. Its nested opaque fields aren't re-audited.
    A true flag isn't permission to perform any support confirmation.
    """

    todo: TodoDetail
    needs_support_confirmation: StrictBool


class SendRequestMessageRequest(_WriteModel):
    """Optional fields use omission, not null. Only member role is public input.

    The app codec also represents privileged roles. Their authorization is
    UNVERIFIED, so they aren't accepted here. No content requirement is inferred.
    """

    content: _WriteText | None = None
    attachments: AttachMediaPayload | None = None
    sender_role: Literal["member"] | None = None


class SendRequestMessageResponse(CasaModel):
    """Required message envelope, reusing RequestMessage without new media variants."""

    message: RequestMessage


class UpdateMultiEnumProperty(_WriteModel):
    """Both selection states are encoded. Server deselection semantics are unknown."""

    id: str
    is_selected: StrictBool


class UpdateEntityProperty(_WriteModel):
    """String-valued write property, not an arbitrary read-model scalar.

    The codec doesn't enforce mutual exclusion among the optional value fields.
    Server acceptance of combinations, duplicates and empty values is UNVERIFIED.
    """

    definition_id: str
    value: _WriteText | None = None
    enum_id: str | None = None
    multi_enums: list[UpdateMultiEnumProperty] | None = None


class UpdateEntityPropertiesRequest(_WriteModel):
    """Required props list with optional make/model strings. No null clear operation."""

    make_id: str | None = None
    model_id: str | None = None
    props: list[UpdateEntityProperty]


class BasicMessageResponse(CasaModel):
    """Required status string. The PATCH doesn't return an updated entity."""

    message: StrictStr


def _write_payload(
    body: BaseModel, schema: type[BaseModel], *, exclude_none: bool = True
) -> dict[str, Any]:
    """Revalidate at the I/O boundary, including copied or mutated nested models.

    Accept valid legacy todo bodies without accepting their permissive extras.
    Validate strict instances directly so model_copy's unknown fields can't hide
    behind serialization. Python-mode dumping adapts valid legacy bodies without
    coercing their values. Only the validated result is JSON-encoded, recursively
    omitting None but preserving empty values. Bodies whose observed wire form
    carries explicit nulls pass ``exclude_none=False``.
    """
    if not isinstance(body, BaseModel):
        raise TypeError("write body must be a Pydantic request model")
    source = (
        body
        if isinstance(body, schema)
        else body.model_dump(mode="python", round_trip=True, warnings=False)
    )
    try:
        validated = schema.model_validate(source)
    except ValidationError as err:
        message = f"Invalid {schema.__name__} write body: {err.error_count()} validation error(s)"
    else:
        return validated.model_dump(mode="json", exclude_none=exclude_none)
    # Raise outside the handler, like _parse. Pydantic's error echoes input
    # values, and an implicit __context__ would leak them in tracebacks.
    raise CasaRequestError(message)
