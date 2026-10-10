"""Models for ``POST /protected/member/bootstrap`` (VERIFIED)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._base import CasaModel, epoch_to_dt
from .enums import HomeStatusField, PaymentMethodTypeField


class UserDeviceRequest(CasaModel):
    device_id: str
    device_name: str
    system_name: str
    system_version: str
    model: str
    language: str
    timezone: str
    app: str
    app_version: str
    app_build: str
    fcm_token: str | None = None
    voip_token: str | None = None


class HomeBadgeCounts(CasaModel):
    computed_at: int
    total: int
    features: dict[str, int] = Field(default_factory=dict)

    @property
    def computed_at_dt(self) -> datetime | None:
        return epoch_to_dt(self.computed_at)


class PendingAgreement(CasaModel):
    """``MemberSimpleHomeAgreement``. ``content`` is the full agreement text."""

    id: str
    name: str
    content: str


class AppUpdate(CasaModel):
    force_update_required: bool
    current_build: str
    min_required_build: str
    message: str
    update_url: str | None = None


class MemberWaitlistEntry(CasaModel):
    id: str
    address_street_number: str
    address_street: str
    address_city: str
    address_state: str
    address_postal_code: str
    status: str
    created_at: int


class MemberSimpleHome(CasaModel):
    id: str
    address_street_number: str
    address_street: str
    address_city: str
    address_state: str
    address_postal_code: str
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    status: HomeStatusField
    card_surcharge_rate: float = 0.0
    has_payment_method: bool = False
    membership_active: bool = False
    is_multi_user_home: bool = False
    has_pending_post_onboarding: bool = False
    pending_agreements: list[PendingAgreement] = Field(default_factory=list)
    address_subpremise: str | None = None
    home_image_url: str | None = None
    home_image_url_cache_key: str | None = None
    payment_description: str | None = None
    payment_method_type: PaymentMethodTypeField | None = None
    payment_method_last4: str | None = None
    payment_method_brand: str | None = None
    membership_name: str | None = None
    membership_plan: Any | None = None
    membership_amount: str | None = None
    membership_next_renewal: int | None = None
    matterport_model_id: str | None = None
    matterport_model_password: str | None = None
    badge_counts: HomeBadgeCounts | None = None
    # Observed in traffic but absent from the app's Codable model.
    plan_state: str | None = None
    route: str | None = None
    is_primary_member: bool | None = None
    past_due_until: int | None = None
    scheduled_change: Any | None = None

    @property
    def display_address(self) -> str:
        street = f"{self.address_street_number} {self.address_street}"
        if self.address_subpremise:
            street = f"{street} {self.address_subpremise}"
        return f"{street}, {self.address_city}, {self.address_state} {self.address_postal_code}"


class Bootstrap(CasaModel):
    id: str
    created_at: int
    phone_number: str
    email: str
    first_name: str
    last_name: str
    homes: list[MemberSimpleHome] = Field(default_factory=list)
    waitlist_entries: list[MemberWaitlistEntry] = Field(default_factory=list)
    is_casa_collective: bool = False
    avatar_url: str | None = None
    avatar_url_cache_key: str | None = None
    app_update: AppUpdate | None = None
    # Observed in traffic but absent from the app's Codable model.
    calendar_sync_active: bool | None = None
    calendar_sync_email: str | None = None
    calendar_sync_insufficient_scope: bool | None = None
    calendar_sync_options: list[Any] = Field(default_factory=list)
    user_prefs: list[Any] = Field(default_factory=list)

    @property
    def created_at_dt(self) -> datetime | None:
        return epoch_to_dt(self.created_at)
