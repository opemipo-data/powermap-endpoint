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

SAME_WEEKDAY_WEEKS = 2  # number of prior same-weekday values to average for estimation
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


def _fill_missing_dates(rows, start_date, end_date, last_real_date, pre_rows=None):
    """Append estimated rows for dates after the last real data point.

    Each missing date is estimated by averaging the supply on the same weekday
    from the previous SAME_WEEKDAY_WEEKS weeks (e.g. if today is Saturday, uses
    last Saturday and the Saturday before that). Falls back gracefully when some
    anchor days have no data. Estimated values are stored in the lookup so they
    can serve as anchors for dates further out.
    Projects at most ESTIMATION_CAP days beyond last_real_date.
    Estimated rows carry {"estimated": True}; real rows get {"estimated": False}.
    """
    for row in rows:
        row["estimated"] = False

    if last_real_date >= end_date:
        return rows

    projection_end = min(end_date, last_real_date + datetime.timedelta(days=ESTIMATION_CAP))
    if projection_end < start_date:
        return rows

    # Build a date-keyed lookup from all real data (pre_rows + in-range rows)
    date_lookup: dict[datetime.date, float] = {
        datetime.date.fromisoformat(r[DATE_COL]): r[HOURS_COL]
        for r in (pre_rows or []) + rows
        if r.get(HOURS_COL) is not None
    }

    if not date_lookup:
        return rows

    current = last_real_date + datetime.timedelta(days=1)
    while current <= projection_end:
        anchor_values = [
            date_lookup[current - datetime.timedelta(weeks=w)]
            for w in range(1, SAME_WEEKDAY_WEEKS + 1)
            if (current - datetime.timedelta(weeks=w)) in date_lookup
        ]
        if anchor_values:
            estimate = round(sum(anchor_values) / len(anchor_values), 2)
            if current >= start_date:
                rows.append({DATE_COL: current.isoformat(), HOURS_COL: estimate, "estimated": True})
            date_lookup[current] = estimate  # allow cascading anchors for further projections
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

    if last_real_date is None or last_real_date < end_date:
        # Estimation will be needed — fetch the anchor window: SAME_WEEKDAY_WEEKS*7 days
        # ending at last_real_date (or before start_date when there are no in-range rows).
        first_estimated = (last_real_date + datetime.timedelta(days=1)) if last_real_date else start_date
        anchor_start = first_estimated - datetime.timedelta(weeks=SAME_WEEKDAY_WEEKS)

        if last_real_date is None:
            # No in-range data — fetch real rows from the anchor window before start_date
            pre_rows = _fetch_range(feeder_id, anchor_start, start_date - datetime.timedelta(days=1), client)
            if pre_rows:
                last_real_date = datetime.date.fromisoformat(pre_rows[-1][DATE_COL])
        elif anchor_start < start_date:
            # Some anchor dates fall before the requested range
            pre_rows = _fetch_range(feeder_id, anchor_start, start_date - datetime.timedelta(days=1), client)

    if last_real_date is not None:
        rows = _fill_missing_dates(rows, start_date, end_date, last_real_date, pre_rows)
    return {
        "feeder_id": feeder_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "average_hours_of_supply": _average(rows),
        "daily": rows,
    }