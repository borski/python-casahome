"""String enums transcribed from the Casa app binary.

Values are the Swift case names. Model fields type these as ``Enum | str`` so an
unseen value from the server degrades to a plain string instead of failing.
The Swift ``unknown`` fallback case is included because the app defines it,
but the server is not expected to send it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field


class MemberSimpleHomeStatus(StrEnum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class PaymentMethodType(StrEnum):
    CARD = "card"
    US_BANK_ACCOUNT = "us_bank_account"
    UNKNOWN = "unknown"


class RequestType(StrEnum):
    CONCIERGE = "concierge"
    HANDYMAN = "handyman"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class RequestStatus(StrEnum):
    PENDING_CONCIERGE = "pending_concierge"
    PENDING_MEMBER = "pending_member"
    PENDING_VENDOR = "pending_vendor"
    COMPLETED = "completed"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


class SenderRole(StrEnum):
    CONCIERGE = "concierge"
    MEMBER = "member"
    VENDOR = "vendor"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class VisitType(StrEnum):
    HANDYMAN = "handyman"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class VendorVisitStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    WRAP_UP = "wrap_up"
    COMPLETED = "completed"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


class TodoStatus(StrEnum):
    PREPARING = "preparing"
    NEEDS_SUPPORT_CONFIRMATION = "needs_support_confirmation"
    NEEDS_INPUT = "needs_input"
    READY_FOR_CONCIERGE = "ready_for_concierge"
    FAILED = "failed"
    MATERIALIZED = "materialized"
    SUGGESTION_CONCIERGE_APPROVAL_PENDING = "suggestion_concierge_approval_pending"
    SUGGESTION_CONCIERGE_APPROVED = "suggestion_concierge_approved"
    SUGGESTION_CONCIERGE_REJECTED = "suggestion_concierge_rejected"
    SUGGESTION_MEMBER_REVIEW_PENDING = "suggestion_member_review_pending"
    SUGGESTION_MEMBER_REJECTED = "suggestion_member_rejected"
    UNKNOWN = "unknown"


class TodoCreatorRole(StrEnum):
    MEMBER = "member"
    CONCIERGE = "concierge"
    VENDOR = "vendor"
    CASA_AI = "casa_ai"
    UNKNOWN = "unknown"


class TodoLaneCardKind(StrEnum):
    TODO = "todo"
    TASK = "task"
    UNKNOWN = "unknown"


class TodoLaneCardState(StrEnum):
    PREPARING = "preparing"
    NEEDS_INPUT = "needs_input"
    READY_FOR_CONCIERGE = "ready_for_concierge"
    FAILED = "failed"
    READY_FOR_SCHEDULING = "ready_for_scheduling"
    UNKNOWN = "unknown"


class PackageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    UNKNOWN = "unknown"


class PackagePickupStatus(StrEnum):
    AWAITING_PICKUP = "awaiting_pickup"
    PICKED_UP = "picked_up"
    DROPPED_OFF = "dropped_off"
    MISSED_PICKUP = "missed_pickup"
    UNKNOWN = "unknown"


class WeatherCondition(StrEnum):
    BLIZZARD = "blizzard"
    BLOWING_SNOW = "blowingSnow"
    BREEZY = "breezy"
    CLEAR = "clear"
    CLOUDY = "cloudy"
    DRIZZLE = "drizzle"
    DUST = "dust"
    FOG = "fog"
    FREEZING_DRIZZLE = "freezingDrizzle"
    FREEZING_RAIN = "freezingRain"
    FLURRIES = "flurries"
    FRIGID = "frigid"
    HAIL = "hail"
    HAZE = "haze"
    HEAVY_RAIN = "heavyRain"
    HEAVY_SNOW = "heavySnow"
    HOT = "hot"
    HURRICANE = "hurricane"
    ISOLATED_THUNDERSTORMS = "isolatedThunderstorms"
    MOSTLY_CLEAR = "mostlyClear"
    MOSTLY_CLOUDY = "mostlyCloudy"
    MIXED_RAIN_AND_SLEET = "mixedRainAndSleet"
    MIXED_RAIN_AND_SNOW = "mixedRainAndSnow"
    MIXED_RAINFALL = "mixedRainfall"
    MIXED_SNOW_AND_SLEET = "mixedSnowAndSleet"
    PARTLY_CLOUDY = "partlyCloudy"
    RAIN = "rain"
    SCATTERED_SHOWERS = "scatteredShowers"
    SCATTERED_SNOW_SHOWERS = "scatteredSnowShowers"
    SCATTERED_THUNDERSTORMS = "scatteredThunderstorms"
    SEVERE_THUNDERSTORM = "severeThunderstorm"
    SHOWERS = "showers"
    SLEET = "sleet"
    SMOKE = "smoke"
    SNOW = "snow"
    SNOW_SHOWERS = "snowShowers"
    THUNDERSTORM = "thunderstorm"
    TORNADO = "tornado"
    TROPICAL_STORM = "tropicalStorm"
    WINDY = "windy"
    UNKNOWN = "unknown"


# Lenient field types. ``left_to_right`` makes pydantic try the enum first and
# fall back to ``str`` for values the app binary didn't know about.
_LTR = Field(union_mode="left_to_right")

HomeStatusField = Annotated[MemberSimpleHomeStatus | str, _LTR]
PaymentMethodTypeField = Annotated[PaymentMethodType | str, _LTR]
RequestTypeField = Annotated[RequestType | str, _LTR]
RequestStatusField = Annotated[RequestStatus | str, _LTR]
SenderRoleField = Annotated[SenderRole | str, _LTR]
VisitTypeField = Annotated[VisitType | str, _LTR]
VendorVisitStatusField = Annotated[VendorVisitStatus | str, _LTR]
TodoStatusField = Annotated[TodoStatus | str, _LTR]
TodoCreatorRoleField = Annotated[TodoCreatorRole | str, _LTR]
TodoLaneCardKindField = Annotated[TodoLaneCardKind | str, _LTR]
TodoLaneCardStateField = Annotated[TodoLaneCardState | str, _LTR]
PackageDirectionField = Annotated[PackageDirection | str, _LTR]
PackagePickupStatusField = Annotated[PackagePickupStatus | str, _LTR]
WeatherConditionField = Annotated[WeatherCondition | str, _LTR]
