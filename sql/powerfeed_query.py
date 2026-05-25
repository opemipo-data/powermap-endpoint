"""PowerFeed query layer.

A single function — `get_supply_in_range` — serves every visualization
in 'Recommended Charts - Power Statistics and Timeline'. The caller
(the router) resolves the (start_date, end_date) window for the chart
it's serving and passes them in. Single-day charts pass start == end.

Logic:
1. Fetch matching daily_supply rows from Supabase, ordered by date.
2. Compute the mean hours_of_supply, skipping nulls.
3. Return a uniform payload — window bounds, daily breakdown, and the
   average — regardless of whether the window is one day or thirty.
   Donut visuals read `average_hours_of_supply`; bar/calendar visuals
   iterate `daily`.

The `client` kwarg is injectable so tests can pass a fake client and
avoid the network.
"""
import datetime

from core import get_supabase_client


TABLE = "daily_supply"
FEEDER_COL = "feeder_id"
DATE_COL = "date"
HOURS_COL = "hours_of_supply"

ESTIMATION_WINDOW = 14  # number of trailing days used to compute the moving average
ESTIMATION_CAP = 30     # max days forward we will project beyond last real data point


def _resolve_client(client):
    return client if client is not None else get_supabase_client()


def _fetch_range(feeder_id, start_date, end_date, client):
    """Fetch daily_supply rows for one feeder between two dates (inclusive)."""
    response = (
        _resolve_client(client)
        .table(TABLE)
        .select(f"{DATE_COL},{HOURS_COL}")
        .eq(FEEDER_COL, feeder_id)
        .gte(DATE_COL, start_date.isoformat())
        .lte(DATE_COL, end_date.isoformat())
        .order(DATE_COL)
        .execute()
    )
    return response.data or []

def _average(rows):
    """Mean hours_of_supply across rows, skipping nulls; 0.0 if no data."""
    hours = [r[HOURS_COL] for r in rows if r.get(HOURS_COL) is not None]
    if not hours:
        return 0.0
    return round(sum(hours) / len(hours), 2)


def _fetch_pre_range(feeder_id, before_date, n, client):
    """Fetch up to n rows immediately before before_date, oldest first."""
    response = (
        _resolve_client(client)
        .table(TABLE)
        .select(f"{DATE_COL},{HOURS_COL}")
        .eq(FEEDER_COL, feeder_id)
        .lt(DATE_COL, before_date.isoformat())
        .order(DATE_COL, desc=True)
        .limit(n)
        .execute()
    )
    return list(reversed(response.data or []))


def _fill_missing_dates(rows, start_date, end_date, last_real_date, pre_rows=None):
    """Append estimated rows for dates after the last real data point.

    Uses a rolling moving average of up to ESTIMATION_WINDOW rows.
    pre_rows pad the window when in-range rows are fewer than ESTIMATION_WINDOW.
    When last_real_date is before start_date (entire range is a gap), the loop
    runs ghost iterations to keep the window rolling before outputting anything.
    Projects at most ESTIMATION_CAP days beyond last_real_date.
    Estimated rows carry {"estimated": True}; real rows get {"estimated": False}.
    """
    for row in rows:
        row["estimated"] = False

    if last_real_date >= end_date:
        return rows

    projection_end = min(end_date, last_real_date + datetime.timedelta(days=ESTIMATION_CAP))
    if projection_end < start_date:
        return rows  # gap is beyond cap, nothing to estimate in range

    window_source = (pre_rows or []) + rows
    window = [r[HOURS_COL] for r in window_source[-ESTIMATION_WINDOW:] if r.get(HOURS_COL) is not None]
    if not window:
        return rows

    current = last_real_date + datetime.timedelta(days=1)
    while current <= projection_end:
        estimate = round(sum(window) / len(window), 2)
        if current >= start_date:
            rows.append({DATE_COL: current.isoformat(), HOURS_COL: estimate, "estimated": True})
        window = window[1:] + [estimate]
        current += datetime.timedelta(days=1)

    return rows


def get_supply_in_range(feeder_id, start_date, end_date, client=None):
    """Return supply data for a feeder between two dates (inclusive).

    Powers all six visualizations. Single-day charts pass the same date
    for both bounds.

    Args:
        feeder_id (int): Feeder primary key.
        start_date (datetime.date): Window start, inclusive.
        end_date (datetime.date): Window end, inclusive.
        client: Optional Supabase client. Defaults to the cached one.

    Returns:
        dict with keys: feeder_id, start_date, end_date,
        average_hours_of_supply, daily (list of {date, hours_of_supply}).
    """
    rows = _fetch_range(feeder_id, start_date, end_date, client)

    pre_rows = []
    last_real_date = None

    if rows:
        last_real_date = datetime.date.fromisoformat(rows[-1][DATE_COL])
        if last_real_date < end_date and len(rows) < ESTIMATION_WINDOW:
            needed = ESTIMATION_WINDOW - len(rows)
            pre_rows = _fetch_pre_range(feeder_id, start_date, needed, client)
    else:
        pre_rows = _fetch_pre_range(feeder_id, start_date, ESTIMATION_WINDOW, client)
        if pre_rows:
            last_real_date = datetime.date.fromisoformat(pre_rows[-1][DATE_COL])

    if last_real_date is not None:
        rows = _fill_missing_dates(rows, start_date, end_date, last_real_date, pre_rows)
    return {
        "feeder_id": feeder_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "average_hours_of_supply": _average(rows),
        "daily": rows,
    }