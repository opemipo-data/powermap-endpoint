"""Tests for utils and sql.powerfeed_query."""
import datetime

import pytest

from sql import powerfeed_query as q
from utils import (
    FeederMatchRequest,
    Lookback,
    SupplyRequest,
    get_lookback_range,
    get_month_range,
    validate_feeder_match_request,
    validate_supply_request,
)


END = datetime.date(2026, 5, 19)


# --- get_lookback_range (pure computation) ----------------------------------

def test_lookback_today():
    start, end = get_lookback_range(END, Lookback.today)
    assert start == end == END


def test_lookback_yesterday():
    start, end = get_lookback_range(END, Lookback.yesterday)
    assert start == end == datetime.date(2026, 5, 18)


def test_lookback_last_7_days():
    start, end = get_lookback_range(END, Lookback.last_7_days)
    assert start == datetime.date(2026, 5, 13)
    assert end == END
    assert (end - start).days + 1 == 7


def test_lookback_last_30_days():
    start, end = get_lookback_range(END, Lookback.last_30_days)
    assert start == datetime.date(2026, 4, 20)
    assert end == END
    assert (end - start).days + 1 == 30


def test_lookback_custom_date():
    start, end = get_lookback_range(END, Lookback.custom_date)
    assert start == end == END


def test_lookback_custom_range():
    s = datetime.date(2026, 5, 1)
    start, end = get_lookback_range(END, Lookback.custom_range, start_date=s)
    assert start == s
    assert end == END


def test_lookback_none_no_start_date_returns_single_day():
    start, end = get_lookback_range(END)
    assert start == end == END


def test_lookback_none_with_start_date_returns_range():
    s = datetime.date(2026, 5, 10)
    start, end = get_lookback_range(END, start_date=s)
    assert start == s
    assert end == END


# --- validate_feeder_match_request ------------------------------------------

def test_validate_feeder_match_rejects_empty_address():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_feeder_match_request(FeederMatchRequest(address=""))


def test_validate_feeder_match_rejects_whitespace_address():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_feeder_match_request(FeederMatchRequest(address="   "))


def test_validate_feeder_match_accepts_valid_address():
    validate_feeder_match_request(FeederMatchRequest(address="12 Allen Avenue, Lagos"))


# --- validate_supply_request ------------------------------------------------

def _supply_body(**kwargs):
    defaults = {"feeder_id": 1, "end_date": END}
    return SupplyRequest(**{**defaults, **kwargs})


def test_validate_supply_rejects_zero_feeder_id():
    with pytest.raises(ValueError, match="positive integer"):
        validate_supply_request(_supply_body(feeder_id=0))


def test_validate_supply_rejects_negative_feeder_id():
    with pytest.raises(ValueError, match="positive integer"):
        validate_supply_request(_supply_body(feeder_id=-5))


def test_validate_supply_custom_range_missing_start():
    with pytest.raises(ValueError, match="start_date is required"):
        validate_supply_request(_supply_body(lookback=Lookback.custom_range))


def test_validate_supply_custom_range_start_after_end():
    with pytest.raises(ValueError, match="must not be after"):
        validate_supply_request(_supply_body(
            lookback=Lookback.custom_range,
            start_date=datetime.date(2026, 6, 1),
        ))


def test_validate_supply_custom_range_exceeds_30_days():
    with pytest.raises(ValueError, match="30 days"):
        validate_supply_request(_supply_body(
            lookback=Lookback.custom_range,
            start_date=datetime.date(2026, 4, 1),
        ))


def test_validate_supply_custom_range_exactly_30_days_is_allowed():
    validate_supply_request(_supply_body(
        lookback=Lookback.custom_range,
        start_date=END - datetime.timedelta(days=29),
    ))


def test_validate_supply_no_lookback_start_after_end_raises():
    with pytest.raises(ValueError, match="must not be after"):
        validate_supply_request(_supply_body(start_date=datetime.date(2026, 6, 1)))


def test_validate_supply_passes_for_valid_today_lookback():
    validate_supply_request(_supply_body(lookback=Lookback.today))


def test_validate_supply_passes_for_valid_custom_range():
    validate_supply_request(_supply_body(
        lookback=Lookback.custom_range,
        start_date=datetime.date(2026, 5, 10),
    ))


# --- get_month_range --------------------------------------------------------

def test_month_range_non_leap_february():
    start, end = get_month_range(2026, 2)
    assert start == datetime.date(2026, 2, 1)
    assert end == datetime.date(2026, 2, 28)


def test_month_range_leap_february():
    _, end = get_month_range(2024, 2)
    assert end == datetime.date(2024, 2, 29)


def test_month_range_december():
    start, end = get_month_range(2026, 12)
    assert start == datetime.date(2026, 12, 1)
    assert end == datetime.date(2026, 12, 31)


def test_month_range_rejects_month_zero():
    with pytest.raises(ValueError):
        get_month_range(2026, 0)


def test_month_range_rejects_month_thirteen():
    with pytest.raises(ValueError):
        get_month_range(2026, 13)


# --- get_supply_in_range ----------------------------------------------------

class _Response:
    def __init__(self, data):
        self.data = data


class FakeSupabase:
    """Records the fluent-call chain and returns canned rows."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.calls = {"eq": []}

    def table(self, name):
        self.calls["table"] = name
        return self

    def select(self, cols):
        self.calls["select"] = cols
        return self

    def eq(self, col, val):
        self.calls["eq"].append((col, val))
        return self

    def gte(self, col, val):
        self.calls["gte"] = (col, val)
        return self

    def lte(self, col, val):
        self.calls["lte"] = (col, val)
        return self

    def lt(self, col, val):
        self.calls["lt"] = (col, val)
        return self

    def order(self, col, desc=False):
        self.calls["order"] = (col, desc)
        return self

    def limit(self, n):
        self.calls["limit"] = n
        return self

    def execute(self):
        return _Response(self._rows)


def test_supply_in_range_returns_uniform_shape():
    rows = [
        {"date": "2026-05-13", "hours_of_supply": 10.0},
        {"date": "2026-05-14", "hours_of_supply": 14.0},
    ]
    fake = FakeSupabase(rows=rows)
    result = q.get_supply_in_range(
        feeder_id=1,
        start_date=datetime.date(2026, 5, 13),
        end_date=datetime.date(2026, 5, 14),
        client=fake,
    )
    assert result == {
        "feeder_id": 1,
        "start_date": "2026-05-13",
        "end_date": "2026-05-14",
        "average_hours_of_supply": pytest.approx(12.0),
        "daily": rows,
    }


def test_supply_in_range_single_day():
    fake = FakeSupabase(rows=[{"date": "2026-05-19", "hours_of_supply": 14.5}])
    target = datetime.date(2026, 5, 19)
    result = q.get_supply_in_range(
        feeder_id=42, start_date=target, end_date=target, client=fake,
    )
    assert fake.calls["gte"] == ("date", "2026-05-19")
    assert fake.calls["lte"] == ("date", "2026-05-19")
    assert result["average_hours_of_supply"] == 14.5
    assert result["daily"] == [{"date": "2026-05-19", "hours_of_supply": 14.5}]


def test_supply_in_range_ignores_null_hours_in_average():
    rows = [
        {"date": "2026-05-13", "hours_of_supply": 10.0},
        {"date": "2026-05-14", "hours_of_supply": None},
        {"date": "2026-05-15", "hours_of_supply": 14.0},
    ]
    fake = FakeSupabase(rows=rows)
    result = q.get_supply_in_range(
        feeder_id=1,
        start_date=datetime.date(2026, 5, 13),
        end_date=datetime.date(2026, 5, 15),
        client=fake,
    )
    assert result["average_hours_of_supply"] == pytest.approx(12.0)


def test_supply_in_range_empty_returns_zero_average():
    fake = FakeSupabase(rows=[])
    result = q.get_supply_in_range(
        feeder_id=1,
        start_date=datetime.date(2026, 5, 13),
        end_date=datetime.date(2026, 5, 19),
        client=fake,
    )
    assert result["average_hours_of_supply"] == 0.0
    assert result["daily"] == []


def test_supply_in_range_filters_and_selects_expected_columns():
    fake = FakeSupabase(rows=[])
    q.get_supply_in_range(
        feeder_id=99,
        start_date=datetime.date(2026, 5, 19),
        end_date=datetime.date(2026, 5, 19),
        client=fake,
    )
    assert fake.calls["table"] == "daily_supply"
    assert ("feeder_id", 99) in fake.calls["eq"]
    assert fake.calls["select"] == "date,hours_of_supply"
    assert fake.calls["order"] == "date"


# --- /supply endpoint (JSON body) -------------------------------------------

def _patched_client(monkeypatch, captured):
    """Return a TestClient with get_supply_in_range replaced by a spy."""
    from fastapi.testclient import TestClient
    import router.power_feed_app as mod

    def fake_supply(feeder_id, start_date, end_date, client=None):
        captured["start"] = start_date
        captured["end"] = end_date
        return {
            "feeder_id": feeder_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "average_hours_of_supply": 0.0,
            "daily": [],
        }

    monkeypatch.setattr(mod, "get_supply_in_range", fake_supply)
    return TestClient(mod.app)


def test_supply_today_lookback(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-19", "lookback": "today"})
    assert response.status_code == 200
    assert captured["start"] == captured["end"] == datetime.date(2026, 5, 19)


def test_supply_yesterday_lookback(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-19", "lookback": "yesterday"})
    assert response.status_code == 200
    assert captured["start"] == captured["end"] == datetime.date(2026, 5, 18)


def test_supply_last_7_days_lookback(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-19", "lookback": "last_7_days"})
    assert response.status_code == 200
    assert captured["start"] == datetime.date(2026, 5, 13)
    assert captured["end"] == datetime.date(2026, 5, 19)


def test_supply_last_30_days_lookback(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-19", "lookback": "last_30_days"})
    assert response.status_code == 200
    assert captured["start"] == datetime.date(2026, 4, 20)
    assert captured["end"] == datetime.date(2026, 5, 19)


def test_supply_custom_date_lookback(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-15", "lookback": "custom_date"})
    assert response.status_code == 200
    assert captured["start"] == captured["end"] == datetime.date(2026, 5, 15)


def test_supply_custom_range_lookback(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={
        "feeder_id": 1,
        "end_date": "2026-05-19",
        "lookback": "custom_range",
        "start_date": "2026-05-10",
    })
    assert response.status_code == 200
    assert captured["start"] == datetime.date(2026, 5, 10)
    assert captured["end"] == datetime.date(2026, 5, 19)


def test_supply_no_lookback_single_day(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-19"})
    assert response.status_code == 200
    assert captured["start"] == captured["end"] == datetime.date(2026, 5, 19)


def test_supply_no_lookback_with_start_date(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={
        "feeder_id": 1,
        "end_date": "2026-05-19",
        "start_date": "2026-05-10",
    })
    assert response.status_code == 200
    assert captured["start"] == datetime.date(2026, 5, 10)
    assert captured["end"] == datetime.date(2026, 5, 19)


def test_supply_custom_range_missing_start_returns_400(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 1, "end_date": "2026-05-19", "lookback": "custom_range"})
    assert response.status_code == 400


def test_supply_custom_range_exceeds_30_days_returns_400(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={
        "feeder_id": 1,
        "end_date": "2026-05-19",
        "lookback": "custom_range",
        "start_date": "2026-04-01",
    })
    assert response.status_code == 400


def test_supply_invalid_feeder_id_returns_400(monkeypatch):
    captured = {}
    client = _patched_client(monkeypatch, captured)
    response = client.post("/supply", json={"feeder_id": 0, "end_date": "2026-05-19"})
    assert response.status_code == 400


# --- Router wiring ----------------------------------------------------------

def test_router_registers_endpoints():
    from router.power_feed_app import app

    paths = {route.path for route in app.routes}
    assert "/supply" in paths
    assert "/feeders/match" in paths
