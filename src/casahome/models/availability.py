"""Static availability detail, never slot submission. UNVERIFIED wire shape.

Fields inferred from the app. Status remains a string so new values survive.
Integer times are retained without promoting their units to observed evidence.
"""

from casahome.models._base import CasaModel


class MemberAvailabilitySummary(CasaModel):
    id: str
    request_id: str
    home_id: str
    status: str
    slot_count: int
    first_submitted_at: int | None = None
    last_submitted_at: int | None = None
    created_at: int


class MemberAvailabilitySlot(CasaModel):
    id: str
    member_availability_request_id: str
    start_time: int
    end_time: int


class MemberAvailabilityConstraints(CasaModel):
    snap_minutes: int
    min_slot_minutes: int
    default_duration_minutes: int
    lead_time_minutes: int


class MemberAvailabilityDetail(CasaModel):
    availability_request: MemberAvailabilitySummary
    slots: list[MemberAvailabilitySlot]
    home_timezone: str
    constraints: MemberAvailabilityConstraints
