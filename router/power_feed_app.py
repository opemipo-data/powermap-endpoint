"""FastAPI endpoints for PowerFeed visualizations.

Two endpoints:

- POST /feeders/match: geocodes an address and returns matching feeders.
- POST /supply: returns power supply data for a feeder over a time window.

Both endpoints receive their parameters as a JSON request body.
Validation is handled by validate_feeder_match_request and
validate_supply_request in utils.py before any processing occurs.

The /supply window is driven by the SupplyRequest body:
    feeder_id  (required) — feeder primary key
    end_date   (required) — upper bound of the window
    lookback   (optional) — preset window: today, yesterday, last_7_days,
                            last_30_days, custom_date, or custom_range
    start_date (optional) — lower bound; required when lookback=custom_range

Behaviour when lookback is omitted:
    - start_date provided → range from start_date to end_date
    - start_date omitted  → single day (end_date to end_date)
"""
from fastapi import FastAPI, HTTPException

from core import get_supabase_client
from schemas import FeederMatchRequest, FeederMatchResponse, LgaAverageRequest, LgaAverageResponse, StateAverageRequest, StateAverageResponse, SupplyRequest, SupplyResponse
from sql.feeder_lookup import match_feeders, resolve_adm2_pcode
from sql.powerfeed_query import get_supply_in_range
from utils import geocode_nominatim, get_lookback_range, validate_feeder_match_request, validate_supply_request

app = FastAPI(title="PowerFeed API")


@app.post("/feeders/match", response_model=FeederMatchResponse)
def find_feeder_for_address(body: FeederMatchRequest):
    """Find feeders that serve a given address."""
    try:
        validate_feeder_match_request(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    geo = geocode_nominatim(body.address)
    if not geo:
        raise HTTPException(status_code=422, detail="Address could not be geocoded")

    adm2_pcode = resolve_adm2_pcode(geo.get("lga"))
    if not adm2_pcode:
        raise HTTPException(status_code=404, detail="Could not resolve LGA for this address")

    feeders = match_feeders(
        address=geo["formatted"].split(',', 1)[0],
        route=geo.get("route"),
        neighborhood=geo.get("neighborhood"),
        sublocality=geo.get("sublocality"),
        adm2_pcode=adm2_pcode,
    )

    return {
        "address": geo["formatted"],
        "geocoded": {
            "lat": geo["lat"],
            "lng": geo["lng"],
            "route": geo.get("route"),
            "neighborhood": geo.get("neighborhood"),
            "sublocality": geo.get("sublocality"),
            "lga": geo.get("lga"),
        },
        "feeders": feeders,
    }


@app.post("/supply", response_model=SupplyResponse)
def supply(body: SupplyRequest):
    """Return power supply data for a feeder over a resolved time window."""
    try:
        validate_supply_request(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resolved_start, resolved_end = get_lookback_range(
        body.end_date, body.lookback, body.start_date
    )
    return get_supply_in_range(body.feeder_id, resolved_start, resolved_end)

@app.post("/lgas/average", response_model=LgaAverageResponse)
def lga_average(body: LgaAverageRequest):
    """Return the average hours of supply across all feeders in an LGA."""
    adm2_pcode = resolve_adm2_pcode(body.lga)
    if not adm2_pcode:
        raise HTTPException(status_code=404, detail="LGA not found")

    resolved_start, resolved_end = get_lookback_range(
        body.end_date, body.lookback, body.start_date
    )

    result = (
        get_supabase_client()
        .rpc("get_lga_supply_avg", {
            "p_adm2_pcode": adm2_pcode,
            "p_start": resolved_start.isoformat(),
            "p_end": resolved_end.isoformat(),
        })
        .execute()
    )

    return {
        "lga": body.lga,
        "adm2_pcode": adm2_pcode,
        "start_date": resolved_start.isoformat(),
        "end_date": resolved_end.isoformat(),
        "average_hours_of_supply": result.data or 0.0,
    }
    
@app.post("/states/average", response_model=StateAverageResponse)
def state_average(body: StateAverageRequest):
    """Return the average hours of supply across all feeders in a state."""
    resolved_start, resolved_end = get_lookback_range(
        body.end_date, body.lookback, body.start_date
    )

    result = (
        get_supabase_client()
        .rpc("get_state_supply_avg", {
            "p_state": body.state,
            "p_start": resolved_start.isoformat(),
            "p_end": resolved_end.isoformat(),
        })
        .execute()
    )

    return {
        "state": body.state,
        "start_date": resolved_start.isoformat(),
        "end_date": resolved_end.isoformat(),
        "average_hours_of_supply": result.data or 0.0,
    }
    
    
    
