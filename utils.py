import calendar
import datetime
import os
from typing import Optional

import requests
from dotenv import load_dotenv

from schemas.requests import FeederMatchRequest, Lookback, SupplyRequest

load_dotenv()

__all__ = [
    "FeederMatchRequest",
    "Lookback",
    "SupplyRequest",
    "validate_feeder_match_request",
    "validate_supply_request",
    "get_lookback_range",
    "get_month_range",
    "geocode_nominatim",
    "geocode_location",
]


def validate_feeder_match_request(body: FeederMatchRequest) -> None:
    """Validate a feeder match request body. Raises ValueError on failure."""
    has_address = bool(body.address and body.address.strip())
    has_coords = body.lat is not None and body.lng is not None
    if not has_address and not has_coords:
        raise ValueError("provide either address or both lat and lng")


def validate_supply_request(body: SupplyRequest) -> None:
    """Validate a supply request body. Raises ValueError on failure.

    Rules:
    - feeder_id must be a positive integer.
    - custom_range requires start_date.
    - start_date must not be after end_date when provided.
    - custom_range window cannot exceed 30 days.
    """
    if body.feeder_id <= 0:
        raise ValueError("feeder_id must be a positive integer")
    if body.lookback == Lookback.custom_range:
        if body.start_date is None:
            raise ValueError("start_date is required for custom_range")
        if body.start_date > body.end_date:
            raise ValueError("start_date must not be after end_date")
        if (body.end_date - body.start_date).days + 1 > 30:
            raise ValueError("custom_range window cannot exceed 30 days")
    elif body.start_date is not None and body.start_date > body.end_date:
        raise ValueError("start_date must not be after end_date")


def get_lookback_range(
    end_date: datetime.date,
    lookback: Optional[Lookback] = None,
    start_date: Optional[datetime.date] = None,
) -> tuple[datetime.date, datetime.date]:
    """Return (start_date, end_date) for the given lookback mode.

    Pure computation — assumes input has already been validated by
    validate_supply_request.
    """
    if lookback == Lookback.yesterday:
        day = end_date - datetime.timedelta(days=1)
        return day, day
    if lookback == Lookback.last_7_days:
        return end_date - datetime.timedelta(days=6), end_date
    if lookback == Lookback.last_30_days:
        return end_date - datetime.timedelta(days=29), end_date
    if lookback == Lookback.custom_range:
        return start_date, end_date
    if lookback in (Lookback.today, Lookback.custom_date) or start_date is None:
        return end_date, end_date
    return start_date, end_date


def get_month_range(year, month):
    """Return a (start_date, end_date) tuple for a specific calendar month."""
    start_date = datetime.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime.date(year, month, last_day)
    return start_date, end_date


def geocode_nominatim(address):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "jsonv2",
        "addressdetails": 1,
        "countrycodes": "ng",
        "limit": 1,
    }
    headers = {"User-Agent": "PowerFeed/1.0"}

    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    results = response.json()

    if not results:
        return None

    r = results[0]
    addr = r.get("address", {})

    return {
        "formatted": r.get("display_name"),
        "lat": float(r["lat"]),
        "lng": float(r["lon"]),
        "route": addr.get("road"),
        "neighborhood": addr.get("neighbourhood") or addr.get("suburb"),
        "sublocality": addr.get("city_district") or addr.get("suburb"),
        "lga": addr.get("county") or addr.get("city"),
        "state": addr.get("state"),
    }


def geocode_nominatim_reverse(lat: float, lng: float):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lng,
        "format": "jsonv2",
        "addressdetails": 1,
    }
    headers = {"User-Agent": "PowerFeed/1.0"}

    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    r = response.json()

    if "error" in r:
        return None

    addr = r.get("address", {})
    return {
        "formatted": r.get("display_name"),
        "lat": float(r["lat"]),
        "lng": float(r["lon"]),
        "route": addr.get("road"),
        "neighborhood": addr.get("neighbourhood") or addr.get("suburb"),
        "sublocality": addr.get("city_district") or addr.get("suburb"),
        "lga": addr.get("county") or addr.get("city"),
        "state": addr.get("state"),
    }


def geocode_location(lat: float, lng: float):
    api_key = os.getenv("API_KEY")
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lng}",
        "key": api_key,
        "result_type": "street_address|route|neighborhood|sublocality|locality|administrative_area_level_2",
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    if data["status"] != "OK" or not data["results"]:
        return None

    result = data["results"][0]
    
    print(result)  # Debugging statement
    
    components = result["address_components"]
    geometry = result["geometry"]["location"]

    type_map = {}
    for comp in components:
        for t in comp["types"]:
            type_map[t] = comp["long_name"]

    return {
        "formatted": result["formatted_address"],
        "lat": geometry["lat"],
        "lng": geometry["lng"],
        "route": type_map.get("route"),
        "neighborhood": type_map.get("neighborhood"),
        "sublocality": type_map.get("sublocality") or type_map.get("sublocality_level_1"),
        "lga": type_map.get("administrative_area_level_2"),
        "state": type_map.get("administrative_area_level_1"),
    }
