from typing import List, Optional

from pydantic import BaseModel


class GeocodedLocation(BaseModel):
    lat: float
    lng: float
    route: Optional[str] = None
    neighborhood: Optional[str] = None
    sublocality: Optional[str] = None
    lga: Optional[str] = None


class Feeder(BaseModel):
    feeder_id: int
    feeder_name: str
    disco: str
    band: str
    location: Optional[str] = None
    street: Optional[str] = None
    match_score: float


class FeederMatchResponse(BaseModel):
    address: str
    geocoded: GeocodedLocation
    feeder: Feeder


class LocationDetailsResponse(BaseModel):
    address: str
    geocoded: GeocodedLocation
    feeder: int
    disco: str
    band: str


class DailySupplyEntry(BaseModel):
    date: str
    hours_of_supply: Optional[float] = None
    estimated: bool = False


class SupplyResponse(BaseModel):
    feeder_id: int
    start_date: str
    end_date: str
    average_hours_of_supply: float
    daily: List[DailySupplyEntry]


class LgaAverageResponse(BaseModel):
    lga: str
    adm2_pcode: str
    start_date: str
    end_date: str
    average_hours_of_supply: float


class StateAverageResponse(BaseModel):
    state: str
    start_date: str
    end_date: str
    average_hours_of_supply: float


class TariffEstimateResponse(BaseModel):
    disco: str
    band: str
    min_monthly_cost: float
    max_monthly_cost: float


class AppliancesByCategoryResponse(BaseModel):
    category: str
    appliances: List[str]
