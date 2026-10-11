"""Mailbox and package models (UNVERIFIED endpoints).

Mailbox models use ISO 8601 string timestamps. Packages use epoch seconds.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ._base import CasaModel
from .enums import PackageDirectionField, PackagePickupStatusField


class MailboxAddress(CasaModel):
    line1: str
    city: str
    state: str
    postal_code: str
    line2: str | None = None


class MailboxQuota(CasaModel):
    month: str
    used: int
    included: int
    overage_rate_usd_cents: int
    resets_on: str | None = None


class MailboxRecipient(CasaModel):
    id: str
    kind: str
    always_included: bool = False
    first_name: str | None = None
    last_name: str | None = None
    business_name: str | None = None
    is_primary: bool | None = None


class MemberMailbox(CasaModel):
    id: str
    status: str
    onboarding_status: str
    address: MailboxAddress
    quota: MailboxQuota
    claimed_at: str
    recipients: list[MailboxRecipient] = Field(default_factory=list)
    auto_archive_days: int | None = None


class MailboxPlan(CasaModel):
    monthly_piece_quota: int
    overage_rate_usd_cents: int


class MailboxClaimResponse(CasaModel):
    """Body from claiming a mailbox. VERIFIED (live, 2026-10)."""

    mailbox: MemberMailbox


class MailboxOverviewResponse(CasaModel):
    mailbox: MemberMailbox | None = None
    plan: MailboxPlan | None = None


class MailboxMailItem(CasaModel):
    id: str
    scan_status: str
    received_at: str
    is_returned_to_sender: bool = False
    check_detected: bool = False
    sender: str | None = None
    addressed_to: str | None = None
    summary: str | None = None
    scan_notice_type: str | None = None
    clear_at: str | None = None
    forward_status: str | None = None
    forward_tracking_number: str | None = None
    shred_status: str | None = None
    deposit_status: str | None = None
    archived_at: str | None = None
    read_at: str | None = None
    envelope_image_url: str | None = None


class MailboxMailItemsResponse(CasaModel):
    mail_items: list[MailboxMailItem] = Field(default_factory=list)


class TrackingHistoryData(CasaModel):
    id: str
    source: str
    message: str
    timestamp: int
    status_display_name: str
    status_detail_display_name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PackageCarrierInfo(CasaModel):
    carrier_id: str
    display_name: str
    logo_url: str
    primary_color: str
    pickup_eligible: bool = False
    trackable: bool = False
    secondary_color: str | None = None
    pickup_requirements: list[Any] | None = None
    pickup_qr_regex: str | None = None
    pickup_category: str | None = None


class PackageItem(CasaModel):
    id: str
    carrier_id: str
    created_at: int
    updated_at: int
    status: str
    status_detail: str
    direction: PackageDirectionField
    archived: bool = False
    is_pickup: bool = False
    can_archive: bool = False
    suggest_archive: bool = False
    tracking_number: str | None = None
    weight: float | None = None
    est_delivery_date: int | None = None
    signed_by: str | None = None
    service: str | None = None
    container_type: str | None = None
    origin_city: str | None = None
    origin_state: str | None = None
    origin_zip: str | None = None
    origin_country: str | None = None
    name: str | None = None
    tracking_history: list[TrackingHistoryData] = Field(default_factory=list)
    pickup_amazon_location: Any | None = None
    pickup_qr_code: str | None = None
    pickup_image_url: str | None = None
    pickup_image_url_cache_key: str | None = None
    pickup_status: PackagePickupStatusField | None = None
    purchased_item: Any | None = None


class PackagesResponse(CasaModel):
    next_pickup_lockdown: int
    next_pickup_start: int
    next_pickup_end: int
    current_pickup_lockdown: int | None = None
    current_pickup_start: int | None = None
    current_pickup_end: int | None = None
    carriers: list[PackageCarrierInfo] = Field(default_factory=list)
    packages: list[PackageItem] = Field(default_factory=list)
    next_pickup_item_ids: list[str] = Field(default_factory=list)
    current_pickup_item_ids: list[str] = Field(default_factory=list)
    package_auto_archive_days: int | None = None
    package_tracking_inbound_email: str | None = None
