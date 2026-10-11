"""Populated preferences and onboarding responses, plus calendar sync metadata."""

from pydantic import JsonValue

from casahome.models._base import CasaModel


class SchedulingDay(CasaModel):
    day_of_week: int
    label: str
    enabled: bool


class SchedulingTimeOfDay(CasaModel):
    id: str
    window_title: str
    window_time_range: str
    enabled: bool


class SchedulePreferencesResponse(CasaModel):
    days_of_week: list[SchedulingDay]
    times_of_day: list[SchedulingTimeOfDay]


class NotificationChannel(CasaModel):
    channel: str
    enabled: bool
    default_enabled: bool
    required: bool


class NotificationType(CasaModel):
    key: str
    display_name: str
    description: str
    sort_order: int
    channels: list[NotificationChannel]


class NotificationGroup(CasaModel):
    key: str
    display_name: str
    sort_order: int
    types: list[NotificationType]


class NotificationSettingsResponse(CasaModel):
    groups: list[NotificationGroup]


class OnboardingSlot(CasaModel):
    start_time: int
    vendor_ids: list[str]


class OnboardingAvailabilityResponse(CasaModel):
    message: str
    number_of_required_vendors: int
    estimated_visit_duration_seconds: int
    timezone: str | None = None
    available_slots: list[OnboardingSlot]


class OnboardingEvent(CasaModel):
    id: str
    start_at: int
    end_at: int


class OnboardingDetailsResponse(CasaModel):
    calendar_events: list[OnboardingEvent]


class AccessPreferencesResponse(CasaModel):
    home_id: str
    general_instructions: str | None = None
    package_pickup_method: str | None = None
    package_pickup_spot: str | None = None
    package_pickup_call_home_member_id: str | None = None
    package_pickup_general_instructions: str | None = None


class CalendarOption(CasaModel):
    """UNVERIFIED item. Available/display calendars were empty."""

    id: str | None = None
    summary: str | None = None
    color: str | None = None


class CalendarSyncResponse(CasaModel):
    home_id: str
    user_oauth_connected: bool
    user_oauth_insufficient_scope: bool
    calendar_sync_active: bool
    has_active_syncs_in_other_homes: bool
    available_calendars: list[CalendarOption]
    display_calendars: list[CalendarOption]
    user_oauth_email: str | None = None
    google_calendar_id: str | None = None
    google_calendar_summary: str | None = None
    sync_status: str | None = None
    sync_progress: JsonValue = None  # Only null observed, no static structure.
