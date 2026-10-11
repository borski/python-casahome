"""Members, vehicles, utilities, and release notes.

Vehicles and utility services were empty. Their optional item fields are known
from static Codable metadata. Vehicle readings remain opaque JSON until observed.
"""

from pydantic import Field, JsonValue

from casahome.models._base import CasaModel


class HomeMember(CasaModel):
    id: str
    first_name: str
    last_name: str
    user_id: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    date_of_birth: str | None = None
    relationship_to_primary: str | None = None
    avatar_url: str | None = None
    avatar_url_cache_key: str | None = None
    expires_at: int | None = None


class HomeMembersResponse(CasaModel):
    members: list[HomeMember]


class VehiclePowertrain(CasaModel):
    type: str | None = None
    display_name: str | None = None


class HomeVehicle(CasaModel):
    id: str | None = None
    home_id: str | None = None
    status: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    display_name: str | None = None
    vin: str | None = None
    powertrain: VehiclePowertrain | None = None
    permissions: list[str] = Field(default_factory=list)
    last_synced_at: str | None = None
    last_successful_sync_at: str | None = None
    readings: JsonValue = None


class VehiclesResponse(CasaModel):
    vehicles: list[HomeVehicle]


class UtilityInsightsStatement(CasaModel):
    id: str | None = None
    ends_at: int | None = None
    total_amount_usd_due: float | None = None
    service_usage_amount: float | None = None
    service_amount_usd: float | None = None


class UtilityUsageGraphWindow(CasaModel):
    id: str | None = None
    starts_at: int | None = None
    ends_at: int | None = None
    usage_values: list[float] = Field(default_factory=list)


class UtilityUsageGraph(CasaModel):
    id: str | None = None
    period: str | None = None
    windows: list[UtilityUsageGraphWindow] = Field(default_factory=list)


class UtilityInsightsAccount(CasaModel):
    id: str | None = None
    account_number: str | None = None
    address_line: str | None = None
    address_location: str | None = None
    provider_name: str | None = None
    image_url: str | None = None
    image_url_cache_key: str | None = None
    is_selected: bool | None = None
    service_types: list[str] = Field(default_factory=list)
    credential_status: str | None = None


class UtilityInsightsService(CasaModel):
    id: str | None = None
    service_type: str | None = None
    usage_unit: str | None = None
    statements: list[UtilityInsightsStatement] = Field(default_factory=list)
    interval_graphs: list[UtilityUsageGraph] = Field(default_factory=list)
    accounts: list[UtilityInsightsAccount] = Field(default_factory=list)


class UtilitiesInsightsResponse(CasaModel):
    services: list[UtilityInsightsService]


class ReleaseNoteSection(CasaModel):
    id: str
    content: str
    title: str | None = None
    hero_image_url: str | None = None


class ReleaseNote(CasaModel):
    id: str
    title: str
    version: str
    date: int
    min_build_number: int
    sections: list[ReleaseNoteSection]
    max_build_number: int | None = None
    prelude: str | None = None
    hero_image_url: str | None = None


class ReleaseNotesResponse(CasaModel):
    data: list[ReleaseNote]
