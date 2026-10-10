"""Credits models (UNVERIFIED endpoint)."""

from __future__ import annotations

from pydantic import Field

from ._base import CasaModel


class CreditHistory(CasaModel):
    id: str
    issued_at: int
    amount: int
    available_amount: int
    expires_at: int | None = None


class ConsumptionHistory(CasaModel):
    id: str
    date: int
    consumed_amount: int


class MemberCredits(CasaModel):
    home_id: str
    total_available: int
    handyman_hourly_rate_cents: int
    credits_history: list[CreditHistory] = Field(default_factory=list)
    consumption_history: list[ConsumptionHistory] = Field(default_factory=list)
