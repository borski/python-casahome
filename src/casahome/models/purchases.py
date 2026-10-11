"""Read-only purchases. All item lists were empty, item fields are static.

Invoice payment structures, pricing summaries, and return info stay opaque JSON.
No payment or purchase mutation is exposed by these models.
"""

from pydantic import JsonValue

from casahome.models._base import CasaModel


class PurchaseVendor(CasaModel):
    id: str | None = None
    name: str | None = None
    image_url: str | None = None
    image_url_cache_key: str | None = None


class PurchaseApproval(CasaModel):
    id: str | None = None
    home_id: str | None = None
    title: str | None = None
    image_url: str | None = None
    image_cache_key: str | None = None
    vendor: PurchaseVendor | None = None
    unit_price_usd_cents: int | None = None
    max_approved_unit_price_usd_cents: int | None = None
    quantity: int | None = None
    estimated_shipping_price_usd_cents: int | None = None
    estimated_return_window_days: int | None = None
    return_policy_notes: str | None = None
    purchase_link: str | None = None
    member_pricing_summary: JsonValue = None
    updated_at: int | None = None


class ApprovedPurchase(PurchaseApproval):
    item_id: str | None = None
    approved_at: int | None = None
    is_voided: bool | None = None


class PurchasedItem(CasaModel):
    id: str | None = None
    home_id: str | None = None
    title: str | None = None
    image_url: str | None = None
    image_cache_key: str | None = None
    vendor: PurchaseVendor | None = None
    unit_price_usd_cents: int | None = None
    return_policy_notes: str | None = None
    purchase_link: str | None = None
    updated_at: int | None = None
    quantity: int | None = None
    invoice_id: str | None = None
    return_by_date: int | None = None
    purchased_at: int | None = None
    return_info: JsonValue = None


class PurchaseInvoice(CasaModel):
    """Minimal static SimpleInvoice fields. Non-purchase wire items unobserved."""

    id: str | None = None
    date: str | None = None
    date_display: str | None = None
    date_epoch_seconds: int | None = None
    amount: float | None = None
    vendor_name: str | None = None
    status: str | None = None
    type: str | None = None
    member_payment: JsonValue = None
    vendor_payment: JsonValue = None


class PurchasesResponse(CasaModel):
    context_title: str | None = None
    pending_purchase_approvals: list[PurchaseApproval]
    approved_purchases: list[ApprovedPurchase]
    purchased_items: list[PurchasedItem]
    non_purchase_invoices: list[PurchaseInvoice]
    next_package_pickup_by: int | None = None


class ScopedPurchasesResponse(CasaModel):
    """Provisional request/visit linkage to PurchasesResponse (static only).

    Unlike the observed home response, the app model doesn't require
    non_purchase_invoices. Unknown additions still survive as model_extra.
    Scoped route envelopes and populated items remain UNVERIFIED.
    """

    context_title: str | None = None
    pending_purchase_approvals: list[PurchaseApproval]
    approved_purchases: list[ApprovedPurchase]
    purchased_items: list[PurchasedItem]
    next_package_pickup_by: int | None = None


class RequestPurchase(CasaModel):
    """Static preview within visit detail."""

    id: str
    image_url: str | None = None
    image_cache_key: str | None = None
    status: str
