"""Shared model base and helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


class CasaModel(BaseModel):
    """Base for all Casa wire models.

    ``extra="allow"`` is deliberate. Casa ships new fields constantly, and the
    library must not break when it does. Unknown fields ride along in
    ``model_extra``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=False)


def epoch_to_dt(value: int | None) -> datetime | None:
    """Convert Casa's epoch-second integers to aware UTC datetimes."""
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC)
