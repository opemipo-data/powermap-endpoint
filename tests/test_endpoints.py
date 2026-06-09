"""Tests for endpoints not covered by test_query.py.

Covers:
  GET  /
  POST /feeders/match
  POST /lgas/average
  POST /states/average
  GET  /appliances/categories
  GET  /appliances/categories/{category}
  POST /tariff/estimate
  POST /location-details

Also covers _fill_missing_dates (estimation logic in powerfeed_query.py).
"""
import datetime

import pytest
from fastapi.testclient import TestClient

import router.power_feed_app as mod
from router.power_feed_app import app
from sql.powerfeed_query import DATE_COL, HOURS_COL, _fill_missing_dates


# ── shared fixtures & fakes ──────────────────────────────────────────────────

FAKE_GEO = {
    "formatted": "12 Allen Avenue, Ikeja, Lagos",
    "lat": 6.601,
    "lng": 3.352,
    "route": "Allen Avenue",
    "neighborhood": "Ikeja",
    "sublocality": "Ikeja",
    "lga": "Ikeja",
}

FAKE_FEEDER = {
    "feeder_id": 1,
    "feeder_name": "Allen 11kV Feeder",
    "disco": "IKEDC",
    "band": "A",
    "location": "Ikeja",
    "streets": ["Allen Avenue"],
    "mapping_quality": "mapped",
    "match_score": 0.9,
}


class _Response:
    def __init__(self, data):
        self.data = data


class FakeBuilder:
    """Fluent Supabase query-builder stub that always returns a canned _Response."""

    def __init__(self, data):
        self._data = data

    def table(self, *a, **kw):
        return self

    def from_(self, *a, **kw):
        return self

    def select(self, *a, **kw):
        return self

    def eq(self, *a, **kw):
        return self

    def or_(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def rpc(self, *a, **kw):
        return self

    def execute(self):
        return _Response(self._data)


def _fake_supabase(data):
    return FakeBuilder(data)


# ── GET / ────────────────────────────────────────────────────────────────────


def test_health_check_returns_ok():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "PowerFeed" in body["service"]
    assert "version" in body


# ── POST /feeders/match ───────────────────────────────────────────────────────


def test_feeder_match_address_returns_200(monkeypatch):
    monkeypatch.setattr(mod, "geocode_nominatim", lambda address: FAKE_GEO)
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "match_feeders", lambda **kw: [FAKE_FEEDER])
    r = TestClient(app).post("/feeders/match", json={"address": "12 Allen Avenue, Lagos"})
    assert r.status_code == 200
    body = r.json()
    assert body["feeder"]["feeder_id"] == 1
    assert body["feeder"]["disco"] == "IKEDC"
    assert body["geocoded"]["lga"] == "Ikeja"


def test_feeder_match_coords_uses_geocode_location(monkeypatch):
    monkeypatch.setattr(mod, "geocode_location", lambda lat, lng: FAKE_GEO)
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "match_feeders", lambda **kw: [FAKE_FEEDER])
    r = TestClient(app).post("/feeders/match", json={"lat": 6.601, "lng": 3.352})
    assert r.status_code == 200
    assert r.json()["feeder"]["feeder_id"] == 1


def test_feeder_match_no_address_no_coords_returns_400():
    r = TestClient(app).post("/feeders/match", json={})
    assert r.status_code == 400


def test_feeder_match_whitespace_address_returns_400():
    r = TestClient(app).post("/feeders/match", json={"address": "   "})
    assert r.status_code == 400


def test_feeder_match_geocode_fails_returns_422(monkeypatch):
    monkeypatch.setattr(mod, "geocode_nominatim", lambda address: None)
    r = TestClient(app).post("/feeders/match", json={"address": "nowhere"})
    assert r.status_code == 422


def test_feeder_match_lga_not_resolved_returns_404(monkeypatch):
    monkeypatch.setattr(mod, "geocode_nominatim", lambda address: FAKE_GEO)
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: None)
    r = TestClient(app).post("/feeders/match", json={"address": "12 Allen Avenue"})
    assert r.status_code == 404


def test_feeder_match_no_feeders_returns_404(monkeypatch):
    monkeypatch.setattr(mod, "geocode_nominatim", lambda address: FAKE_GEO)
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "match_feeders", lambda **kw: [])
    r = TestClient(app).post("/feeders/match", json={"address": "12 Allen Avenue"})
    assert r.status_code == 404


def test_feeder_match_returns_top_feeder_only(monkeypatch):
    second = {**FAKE_FEEDER, "feeder_id": 2, "feeder_name": "B Feeder", "match_score": 0.5}
    monkeypatch.setattr(mod, "geocode_nominatim", lambda address: FAKE_GEO)
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "match_feeders", lambda **kw: [FAKE_FEEDER, second])
    r = TestClient(app).post("/feeders/match", json={"address": "12 Allen Avenue"})
    assert r.status_code == 200
    assert r.json()["feeder"]["feeder_id"] == 1


# ── POST /lgas/average ────────────────────────────────────────────────────────


def test_lga_average_returns_200(monkeypatch):
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(8.5))
    r = TestClient(app).post("/lgas/average", json={"lga": "Ikeja", "end_date": "2026-05-19"})
    assert r.status_code == 200
    body = r.json()
    assert body["lga"] == "Ikeja"
    assert body["adm2_pcode"] == "NG001"
    assert body["average_hours_of_supply"] == pytest.approx(8.5)
    assert body["start_date"] == body["end_date"] == "2026-05-19"


def test_lga_average_unknown_lga_returns_404(monkeypatch):
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: None)
    r = TestClient(app).post("/lgas/average", json={"lga": "Nowhere", "end_date": "2026-05-19"})
    assert r.status_code == 404


def test_lga_average_null_supabase_data_returns_zero(monkeypatch):
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(None))
    r = TestClient(app).post("/lgas/average", json={"lga": "Ikeja", "end_date": "2026-05-19"})
    assert r.status_code == 200
    assert r.json()["average_hours_of_supply"] == 0.0


def test_lga_average_lookback_window_is_applied(monkeypatch):
    monkeypatch.setattr(mod, "resolve_adm2_pcode", lambda lga, client=None: "NG001")
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(6.0))
    r = TestClient(app).post(
        "/lgas/average",
        json={"lga": "Ikeja", "end_date": "2026-05-19", "lookback": "last_7_days"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start_date"] == "2026-05-13"
    assert body["end_date"] == "2026-05-19"


# ── POST /states/average ──────────────────────────────────────────────────────


def test_state_average_returns_200(monkeypatch):
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(12.3))
    r = TestClient(app).post("/states/average", json={"state": "Lagos", "end_date": "2026-05-19"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "Lagos"
    assert body["average_hours_of_supply"] == pytest.approx(12.3)
    assert "start_date" in body and "end_date" in body


def test_state_average_null_data_returns_zero(monkeypatch):
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(None))
    r = TestClient(app).post("/states/average", json={"state": "Kano", "end_date": "2026-05-19"})
    assert r.status_code == 200
    assert r.json()["average_hours_of_supply"] == 0.0


def test_state_average_lookback_window_is_applied(monkeypatch):
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(10.0))
    r = TestClient(app).post(
        "/states/average",
        json={"state": "Lagos", "end_date": "2026-05-19", "lookback": "last_30_days"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start_date"] == "2026-04-20"
    assert body["end_date"] == "2026-05-19"


# ── GET /appliances/categories ────────────────────────────────────────────────


def test_list_categories_returns_sorted_deduplicated_list(monkeypatch):
    data = [{"category": "Lighting"}, {"category": "Cooling"}, {"category": "Lighting"}]
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(data))
    r = TestClient(app).get("/appliances/categories")
    assert r.status_code == 200
    categories = r.json()
    assert categories == ["Cooling", "Lighting"]


def test_list_categories_skips_null_entries(monkeypatch):
    data = [{"category": "Cooling"}, {"category": None}, {"category": "Lighting"}]
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(data))
    r = TestClient(app).get("/appliances/categories")
    assert r.status_code == 200
    assert None not in r.json()


def test_list_categories_empty_db_returns_empty_list(monkeypatch):
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase([]))
    r = TestClient(app).get("/appliances/categories")
    assert r.status_code == 200
    assert r.json() == []


# ── GET /appliances/categories/{category} ─────────────────────────────────────


def test_appliances_by_category_returns_200(monkeypatch):
    data = [{"appliance": "Ceiling Fan"}, {"appliance": "Standing Fan"}]
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(data))
    r = TestClient(app).get("/appliances/categories/Cooling")
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "Cooling"
    assert set(body["appliances"]) == {"Ceiling Fan", "Standing Fan"}


def test_appliances_by_category_not_found_returns_404(monkeypatch):
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase([]))
    r = TestClient(app).get("/appliances/categories/Unknown")
    assert r.status_code == 404


# ── POST /tariff/estimate ─────────────────────────────────────────────────────

_APPLIANCE_BODY = [
    {"appliance": "Fan", "min_daily_hours": 4.0, "max_daily_hours": 8.0, "qty": 2}
]


def test_tariff_estimate_returns_min_max_cost(monkeypatch):
    data = [{"min_cost": 2500.0, "max_cost": 5000.0}]
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase(data))
    r = TestClient(app).post(
        "/tariff/estimate",
        json={"disco": "IKEDC", "band": "A", "appliances": _APPLIANCE_BODY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["disco"] == "IKEDC"
    assert body["band"] == "A"
    assert body["min_monthly_cost"] == 2500.0
    assert body["max_monthly_cost"] == 5000.0


def test_tariff_estimate_no_tariff_returns_404(monkeypatch):
    monkeypatch.setattr(mod, "get_supabase_client", lambda: _fake_supabase([]))
    r = TestClient(app).post(
        "/tariff/estimate",
        json={"disco": "PHCN", "band": "Z", "appliances": _APPLIANCE_BODY},
    )
    assert r.status_code == 404


def test_tariff_estimate_invalid_appliance_hours_returns_422():
    # max_daily_hours > 24 should fail Pydantic validation
    r = TestClient(app).post(
        "/tariff/estimate",
        json={
            "disco": "IKEDC",
            "band": "A",
            "appliances": [
                {"appliance": "Fan", "min_daily_hours": 4.0, "max_daily_hours": 25.0, "qty": 1}
            ],
        },
    )
    assert r.status_code == 422


# ── POST /location-details ────────────────────────────────────────────────────


def test_location_details_returns_correct_shape(monkeypatch):
    feeder_match_result = {
        "address": "12 Allen Avenue, Ikeja, Lagos",
        "geocoded": {
            "lat": 6.601,
            "lng": 3.352,
            "route": "Allen Avenue",
            "neighborhood": "Ikeja",
            "sublocality": "Ikeja",
            "lga": "Ikeja",
        },
        "feeder": {
            "feeder_id": 7,
            "feeder_name": "Allen 11kV Feeder",
            "disco": "IKEDC",
            "band": "A",
            "location": "Ikeja",
            "streets": [],
            "mapping_quality": "mapped",
            "match_score": 0.9,
        },
    }
    monkeypatch.setattr(mod, "find_feeder_for_address", lambda body: feeder_match_result)
    r = TestClient(app).post("/location-details", json={"address": "12 Allen Avenue, Lagos"})
    assert r.status_code == 200
    body = r.json()
    assert body["feeder"] == 7
    assert body["disco"] == "IKEDC"
    assert body["band"] == "A"
    assert body["address"] == "12 Allen Avenue, Ikeja, Lagos"
    assert "geocoded" in body


# ── _fill_missing_dates (estimation logic) ────────────────────────────────────


def _dr(date_str, hours):
    return {DATE_COL: date_str, HOURS_COL: hours}


def test_fill_missing_no_gap_marks_rows_not_estimated():
    rows = [_dr("2026-05-18", 10.0), _dr("2026-05-19", 12.0)]
    result = _fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 18),
        end_date=datetime.date(2026, 5, 19),
        last_real_date=datetime.date(2026, 5, 19),
    )
    assert len(result) == 2
    assert all(r["estimated"] is False for r in result)


def test_fill_missing_appends_estimated_row_for_gap():
    # May 19 is the last real date; end_date is May 20.
    # Anchors for May 20: May 13 (1 week back) and May 6 (2 weeks back) → avg = (8+12)/2 = 10
    rows = [_dr("2026-05-19", 14.0)]
    pre_rows = [_dr("2026-05-06", 12.0), _dr("2026-05-13", 8.0)]
    result = _fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 19),
        end_date=datetime.date(2026, 5, 20),
        last_real_date=datetime.date(2026, 5, 19),
        pre_rows=pre_rows,
    )
    estimated = [r for r in result if r["estimated"]]
    assert len(estimated) == 1
    assert estimated[0][DATE_COL] == "2026-05-20"
    assert estimated[0][HOURS_COL] == pytest.approx(10.0)


def test_fill_missing_uses_average_of_two_same_weekday_anchors():
    # May 20 is a Wednesday; anchors must be Wednesdays: May 13 (14) and May 6 (6) → avg 10
    rows = [_dr("2026-05-19", 8.0)]
    pre_rows = [_dr("2026-05-06", 6.0), _dr("2026-05-13", 14.0)]
    result = _fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 19),
        end_date=datetime.date(2026, 5, 20),
        last_real_date=datetime.date(2026, 5, 19),
        pre_rows=pre_rows,
    )
    estimated = [r for r in result if r["estimated"]]
    assert len(estimated) == 1
    assert estimated[0][HOURS_COL] == pytest.approx(10.0)


def test_fill_missing_single_anchor_uses_that_value():
    # May 20 is a Wednesday; only May 13 (Wednesday, 1 week back) available — result equals it
    rows = [_dr("2026-05-19", 8.0)]
    pre_rows = [_dr("2026-05-13", 9.0)]   # only 1 week back; 2 weeks back (May 6) missing
    result = _fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 19),
        end_date=datetime.date(2026, 5, 20),
        last_real_date=datetime.date(2026, 5, 19),
        pre_rows=pre_rows,
    )
    estimated = [r for r in result if r["estimated"]]
    assert len(estimated) == 1
    assert estimated[0][HOURS_COL] == pytest.approx(9.0)


def test_fill_missing_no_anchors_produces_no_estimates():
    # No pre_rows and no in-range same-weekday history → nothing estimated
    rows = [_dr("2026-05-19", 10.0)]
    result = _fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 19),
        end_date=datetime.date(2026, 5, 21),
        last_real_date=datetime.date(2026, 5, 19),
        pre_rows=[],
    )
    estimated = [r for r in result if r.get("estimated")]
    assert len(estimated) == 0


def test_fill_missing_caps_at_estimation_cap(monkeypatch):
    import sql.powerfeed_query as pq
    monkeypatch.setattr(pq, "ESTIMATION_CAP", 3)
    rows = [_dr("2026-05-10", 10.0)]
    pre_rows = [_dr("2026-04-26", 10.0), _dr("2026-05-03", 10.0)]
    result = pq._fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 10),
        end_date=datetime.date(2026, 5, 25),
        last_real_date=datetime.date(2026, 5, 10),
        pre_rows=pre_rows,
    )
    estimated = [r for r in result if r.get("estimated")]
    assert len(estimated) <= 3


def test_fill_missing_skips_nulls_in_anchor_lookup():
    # Row with None hours should not enter date_lookup and not be used as anchor
    rows = [_dr("2026-05-19", 10.0)]
    pre_rows = [
        {DATE_COL: "2026-05-12", HOURS_COL: None},  # null anchor — should be ignored
        _dr("2026-05-05", 8.0),
    ]
    result = _fill_missing_dates(
        rows,
        start_date=datetime.date(2026, 5, 19),
        end_date=datetime.date(2026, 5, 20),
        last_real_date=datetime.date(2026, 5, 19),
        pre_rows=pre_rows,
    )
    estimated = [r for r in result if r.get("estimated")]
    if estimated:
        # Only May 5 (2 weeks back) was used as anchor
        assert estimated[0][HOURS_COL] == pytest.approx(8.0)
