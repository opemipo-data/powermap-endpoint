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
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import get_supabase_client
from schemas import AppliancesByCategoryResponse, FeederMatchRequest, FeederMatchResponse, LgaAverageRequest, LgaAverageResponse, LocationDetailsResponse, StateAverageRequest, StateAverageResponse, SupplyRequest, SupplyResponse, TariffEstimateRequest, TariffEstimateResponse
from sql.feeder_lookup import match_feeders, resolve_adm2_pcode
from sql.powerfeed_query import get_supply_in_range
from utils import geocode_nominatim, geocode_nominatim_reverse, get_lookback_range, validate_feeder_match_request, validate_supply_request

app = FastAPI(title="PowerFeed API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000", "http://localhost:5173", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "ok", "service": "PowerFeed API", "version": "0.1.0"}

@app.exception_handler(Exception)
async def global_catch_all_handler(request: Request, exc: Exception):
    """The ultimate fallback handler for unhandled bugs (database down, index out of bounds, etc.)."""
    # Log the full traceback internally for developers to fix
    print(f"Unhandled crash on {request.url.path}: {exc}")
    
    # Hide server internal details from external clients
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "InternalServerError", "detail": "An unexpected system error occurred."},
    )


@app.post("/feeders/match", response_model=FeederMatchResponse)
def find_feeder_for_address(body: FeederMatchRequest):
    """Find feeders that serve a given address."""
    try:
        validate_feeder_match_request(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if body.lat is not None and body.lng is not None:
        geo = geocode_nominatim_reverse(body.lat, body.lng)
    else:
        geo = geocode_nominatim(body.address)
    if not geo:
        raise HTTPException(status_code=422, detail="Location could not be geocoded")

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
    if not feeders:
        raise HTTPException(status_code=404, detail="Could not resolve feeder for this location")

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
        "feeder": feeders[0],
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
        "average_hours_of_supply": round(result.data or 0.0, 2),
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
        "average_hours_of_supply": round(result.data or 0.0, 2),
    }

@app.get("/appliances/categories")
def list_categories():
    """Return all distinct appliance categories."""
    result = (
        get_supabase_client()
        .from_("appliance_ratings")
        .select("category")
        .execute()
    )
    categories = sorted({row["category"] for row in result.data if row["category"]})
    return categories


@app.get("/appliances/categories/{category}", response_model=AppliancesByCategoryResponse)
def list_appliances_by_category(category: str):
    """Return all appliances in a given category."""
    result = (
        get_supabase_client()
        .from_("appliance_ratings")
        .select("appliance")
        .eq("category", category)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")

    return {
        "category": category,
        "appliances": [row["appliance"] for row in result.data],
    }


@app.post("/tariff/estimate", response_model=TariffEstimateResponse)
def tariff_estimate(body: TariffEstimateRequest):
    """Return estimated min/max monthly electricity cost for a list of appliances."""
    result = (
        get_supabase_client()
        .rpc("estimate_monthly_tariff", {
            "p_disco": body.disco,
            "p_band": body.band,
            "p_appliances": [a.model_dump() for a in body.appliances],
        })
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="No tariff found for the given disco and band")

    row = result.data[0]
    return {
        "disco": body.disco,
        "band": body.band,
        "min_monthly_cost": row["min_cost"],
        "max_monthly_cost": row["max_cost"],
    }


@app.post("/location-details", response_model=LocationDetailsResponse)
def location_details(body: FeederMatchRequest):
    """Return details about a specific location."""
    res: FeederMatchResponse = find_feeder_for_address(body)
    print(res)

    return {
        "address": res["address"],
        "geocoded": res["geocoded"],
        "feeder": res["feeder"]["feeder_id"],
        "disco": res["feeder"]["disco"],
        "band": res["feeder"]["band"]
    }
    