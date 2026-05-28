import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Lookback(str, Enum):
    today = "today"
    yesterday = "yesterday"
    last_7_days = "last_7_days"
    last_30_days = "last_30_days"
    custom_date = "custom_date"
    custom_range = "custom_range"


class FeederMatchRequest(BaseModel):
    address: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class _DateRangeRequest(BaseModel):
    end_date: datetime.date = Field(default_factory=datetime.date.today)
    lookback: Optional[Lookback] = None
    start_date: Optional[datetime.date] = None

    @field_validator("end_date")
    @classmethod
    def end_date_not_in_future(cls, v: datetime.date) -> datetime.date:
        if v > datetime.date.today():
            raise ValueError("end_date must not be greater than today")
        return v


class SupplyRequest(_DateRangeRequest):
    feeder_id: int


class LgaAverageRequest(_DateRangeRequest):
    lga: str


class StateAverageRequest(_DateRangeRequest):
    state: str


class ApplianceUsage(BaseModel):
    appliance: str
    min_daily_hours: float = Field(gt=0, le=24)
    max_daily_hours: float = Field(gt=0, le=24)
    qty: int = Field(ge=1)


class TariffEstimateRequest(BaseModel):
    disco: str
    band: str
    appliances: List[ApplianceUsage]