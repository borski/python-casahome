"""Membership summaries, not billing or lifecycle action contracts.

The ``membership/info`` envelope is VERIFIED (live, 2026-10) for an active
membership. Savings remain static and UNVERIFIED. Cents/seconds are retained
as named, without inventing a reporting period, currency or timezone.
"""

from pydantic import JsonValue

from casahome.models._base import CasaModel


class MembershipBenefit(CasaModel):
    # The app's id type isn't known to be a String, so keep it as JSON.
    id: JsonValue
    title: str
    emoji: str
    symbol: str
    description: str


class MembershipDetails(CasaModel):
    """Top-level keys VERIFIED (live, 2026-10) for an active membership.

    The billing-period fields accept epoch integers or strings, since their
    encoding isn't pinned. All newer keys are optional so other membership
    states still parse.
    """

    name: str
    amount: str
    amount_cents: int | None = None
    interval: str
    next_billing_date: int | None = None
    member_since: int | None = None
    benefits: list[MembershipBenefit] | None = None
    status: str | None = None
    cancel_at_period_end: bool | None = None
    current_period_start: int | str | None = None
    current_period_end: int | str | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None


class MembershipSavingsSummary(CasaModel):
    total_time_saved_seconds: int
    total_money_saved_cents: int


class MembershipSavingsBreakdown(CasaModel):
    title: str
    value: str


class MembershipSavingsCategory(CasaModel):
    type: str
    label: str
    color: str
    preview: str | None = None
    is_visible: bool
    time_saved_seconds: int
    money_saved_cents: int
    breakdown: list[MembershipSavingsBreakdown]


class MembershipSavingsMetadata(CasaModel):
    id: str
    created_at: str
    updated_at: str


class MembershipSavings(CasaModel):
    home_id: str
    calculated_at: str
    should_promote: bool
    summary: MembershipSavingsSummary
    categories: list[MembershipSavingsCategory]
    metadata: MembershipSavingsMetadata
