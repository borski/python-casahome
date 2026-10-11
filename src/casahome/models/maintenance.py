"""Autopilot and inventory service history.

Autopilot's populated variants were observed in the saved follow-up response.
Service history lists were empty. Their item fields come from static Codable data.
String discriminators stay open to future server values.
"""

from pydantic import RootModel

from casahome.models._base import CasaModel
from casahome.models.requests import Pagination, RequestCard


class AutopilotRequirementOption(CasaModel):
    type_id: str
    name: str
    symbol_name: str | None = None
    help_center_article_id: str | None = None


class AutopilotRequirementProperty(CasaModel):
    definition_id: str
    entity_type_id: str
    title: str


class AutopilotRequirementRoomProperty(CasaModel):
    definition_id: str
    title: str
    data_type: str
    symbol_name: str | None = None


class AutopilotRequirementRoomCandidate(CasaModel):
    room_id: str
    name: str
    story_name: str
    story_floor_number: int
    duration_minutes: int
    image_url: str | None = None
    image_url_cache_key: str | None = None
    price_usd_cents: int | None = None
    property_value: bool | None = None


class AutopilotPlanRequirement(CasaModel):
    kind: str
    options: list[AutopilotRequirementOption]
    noun_with_article: str | None = None
    property: AutopilotRequirementProperty | None = None
    room_property: AutopilotRequirementRoomProperty | None = None
    room_candidates: list[AutopilotRequirementRoomCandidate] | None = None


class AutopilotIllustration(CasaModel):
    bg_color: str
    url: str | None = None
    url_cache_key: str | None = None


class AutopilotPricingPolicy(CasaModel):
    symbol_name: str
    title: str
    description: str


class AutopilotHomeAssociation(CasaModel):
    id: str
    duration_minutes: int
    enabled: bool | None = None
    price_usd_cents: int | None = None


class AutopilotRoomAssociation(CasaModel):
    id: str
    room_id: str
    room_name: str
    room_story_name: str
    duration_minutes: int
    enabled: bool | None = None
    room_image_url: str | None = None
    room_image_cache_key: str | None = None
    price_usd_cents: int | None = None


class AutopilotEntityAssociation(CasaModel):
    id: str
    entity_id: str
    entity_make: str
    entity_model: str
    duration_minutes: int
    enabled: bool | None = None
    entity_display_name: str | None = None
    entity_location: str | None = None
    entity_image_url: str | None = None
    entity_image_cache_key: str | None = None
    price_usd_cents: int | None = None


class AutopilotPlan(CasaModel):
    plan_id: str
    plan_template_id: str
    title: str
    subtitle: str
    description: str
    applies_to: str
    type: str
    enabled: bool
    illustration: AutopilotIllustration
    asap_schedule_description: str
    pricing_policies: list[AutopilotPricingPolicy]
    fulfillment_policy: str
    savings_percentage: int
    cadence_options: list[str]
    default_cadence: str
    next_projected_occurrence_range_start: str
    next_projected_occurrence_range_end: str
    room_associations: list[AutopilotRoomAssociation]
    entity_associations: list[AutopilotEntityAssociation]
    requirement: AutopilotPlanRequirement | None = None
    handyman_credit_policy: str | None = None
    selected_cadence: str | None = None
    next_desired_occurrence_date: str | None = None
    next_calendar_event_start_at: int | None = None
    home_association: AutopilotHomeAssociation | None = None


class AutopilotIneligiblePlan(CasaModel):
    plan_template_id: str
    title: str
    subtitle: str
    description: str
    type: str
    fulfillment_policy: str
    illustration: AutopilotIllustration
    requirement: AutopilotPlanRequirement


class AutopilotCategory(CasaModel):
    category_id: str
    category_title: str
    category_description: str
    category_rendering_type: str
    plans: list[AutopilotPlan]
    ineligible_plans: list[AutopilotIneligiblePlan]


class AutopilotCategoriesResponse(RootModel[list[AutopilotCategory]]):
    """The wire response is a bare list, not a plans envelope."""


class ServiceHistoryPlan(CasaModel):
    """UNVERIFIED item. Known static fields are optional to tolerate drift."""

    id: str | None = None
    enabled: bool | None = None
    title: str | None = None
    selected_cadence: str | None = None
    next_service_at: int | None = None


class ServiceHistoryItem(CasaModel):
    """UNVERIFIED item from static Codable metadata."""

    task_id: str | None = None
    task_type: str | None = None
    task_title: str | None = None
    task_emoji: str | None = None
    serviced_at: int | None = None
    task_hero_image_url: str | None = None
    task_hero_image_cache_key: str | None = None
    handyman_job_id: str | None = None
    vendor_visit_id: str | None = None
    autopilot_plan_id: str | None = None


class InventoryServiceHistoryResponse(CasaModel):
    autopilot_plans: list[ServiceHistoryPlan]
    history_items: list[ServiceHistoryItem]


class CalendarBusyBlock(CasaModel):
    """UNVERIFIED block from static Codable metadata."""

    start_time: int | None = None
    end_time: int | None = None
    title: str | None = None


class CalendarBusyResponse(CasaModel):
    blocks: list[CalendarBusyBlock]
    google_status: str


class CompletedRequestsResponse(CasaModel):
    """Empty list observed. RequestCard is the existing static item model."""

    kind: str
    items: list[RequestCard]
    pagination: Pagination
