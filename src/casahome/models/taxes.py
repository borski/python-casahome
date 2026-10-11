"""Property tax reads. Only refresh metadata and an empty reports list observed."""

from pydantic import Field

from casahome.models._base import CasaModel


class PropertyTaxRefresh(CasaModel):
    status: str
    next_fetch_at: int | None = None


class PropertyTaxSpecialAssessment(CasaModel):
    id: str | None = None
    name: str | None = None
    amount: float | None = None


class PropertyTaxInstallment(CasaModel):
    id: str | None = None
    total: float | None = None
    due_date: int | None = None
    payment_amount: float | None = None
    payment_date: int | None = None


class PropertyTaxReport(CasaModel):
    id: str | None = None
    report_id: str | None = None
    issued_at: int | None = None
    agency_name: str | None = None
    tax_collector_url: str | None = None
    tax_year_start: int | None = None
    tax_year_end: int | None = None
    land_value: float | None = None
    improvement_value: float | None = None
    total_assessed_value: float | None = None
    total_taxable_value: float | None = None
    total_tax_due: float | None = None
    special_assessments: list[PropertyTaxSpecialAssessment] = Field(default_factory=list)
    installments: list[PropertyTaxInstallment] = Field(default_factory=list)


class PropertyTaxesResponse(CasaModel):
    next_tax_bill_release_at: int | None = None
    refresh: PropertyTaxRefresh | None = None
    reports: list[PropertyTaxReport]
