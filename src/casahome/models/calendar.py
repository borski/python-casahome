"""Visit calendar models (UNVERIFIED endpoint)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._base import CasaModel, epoch_to_dt


class CalendarEvent(CasaModel):
    """``VisitCalendarEvent``. ``kind`` is a Swift enum with associated payloads
    (vendor visit or DTD), so its wire shape is unknown. Kept loose until traffic
    shows it."""

    id: str
    start_time: int
    end_time: int
    kind: Any = None

    @property
    def start_dt(self) -> datetime | None:
        return epoch_to_dt(self.start_time)

    @property
    def end_dt(self) -> datetime | None:
        return epoch_to_dt(self.end_time)


class VisitsCalendarResponse(CasaModel):
    events: list[CalendarEvent] = Field(default_factory=list)
