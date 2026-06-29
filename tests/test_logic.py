"""Tests for the pure pricing logic -- no I/O, fast."""

from datetime import datetime

from app.logic import (
    appliance_cost,
    best_window,
    build_price_curve,
    compute_estimate,
    fmt_hour,
    price_at_hour,
    score_now,
    simulate_by_start_hour,
    window_avg_price,
)

TOU = {
    "name": "Test TOU",
    "structure": "tou",
    "eia_region": "ERCO",
    "periods": [(0, 6, 0.08), (6, 14, 0.14), (14, 20, 0.24), (20, 24, 0.12)],
}
FLAT = {"name": "Test Flat", "structure": "flat", "eia_region": "PJM", "flat_rate": 0.16}


def test_price_at_hour_tou():
    assert price_at_hour(TOU, 2) == 0.08
    assert price_at_hour(TOU, 16) == 0.24
    assert price_at_hour(TOU, 23) == 0.12


def test_price_at_hour_flat():
    assert price_at_hour(FLAT, 0) == 0.16
    assert price_at_hour(FLAT, 17) == 0.16


def test_build_price_curve_length():
    curve = build_price_curve(TOU)
    assert len(curve) == 24
    assert curve[3] == 0.08


def test_appliance_cost():
    # 7200W for 2h at $0.10/kWh = 7.2kW * 2 * 0.10 = $1.44
    assert appliance_cost(7200, 2, 0.10) == 1.44


def test_score_now_buckets():
    curve = build_price_curve(TOU)
    assert score_now(0.08, curve)["level"] == "green"
    assert score_now(0.24, curve)["level"] == "red"
    assert score_now(0.14, curve)["level"] in {"yellow", "green"}


def test_score_now_flat():
    curve = build_price_curve(FLAT)
    assert score_now(0.16, curve)["level"] == "flat"


def test_best_window_finds_cheapest():
    curve = build_price_curve(TOU)
    # From 14:00 (peak), cheapest 2h window should be overnight (0-6, $0.08).
    win = best_window(curve, 2, from_hour=14)
    assert win["avg_price"] == 0.08
    assert win["length_hours"] == 2


def test_best_window_respects_horizon():
    curve = build_price_curve(TOU)
    win = best_window(curve, 3, from_hour=0)
    assert 0 <= win["start_hour"] < 24


def test_fmt_hour():
    assert fmt_hour(0) == "12 AM"
    assert fmt_hour(12) == "12 PM"
    assert fmt_hour(16) == "4 PM"


def test_compute_estimate_with_appliance():
    appl = {"label": "EV", "watts": 7200, "default_hours": 4.0}
    demand = {"curve": [0.5] * 24, "source": "mock"}
    now = datetime(2026, 1, 1, 16, 0)  # 4pm peak
    r = compute_estimate(TOU, appl, 2.0, demand, now=now)
    assert r["current_price"] == 0.24
    assert r["appliance"]["cost_now"] > r["appliance"]["cost_best"]
    assert r["appliance"]["savings"] > 0
    assert r["score"]["level"] == "red"


def test_compute_estimate_no_appliance():
    demand = {"curve": [0.5] * 24, "source": "mock"}
    r = compute_estimate(TOU, None, 1.0, demand, now=datetime(2026, 1, 1, 3, 0))
    assert "appliance" not in r
    assert r["current_price"] == 0.08


def test_window_avg_price_wraps():
    curve = build_price_curve(TOU)
    # 23:00 ($0.12) + 00:00 ($0.08) avg = 0.10
    assert window_avg_price(curve, 23, 2) == 0.10


def test_simulate_by_start_hour_shape():
    curve = build_price_curve(TOU)
    sim = simulate_by_start_hour(curve, 7200, 2.0)
    assert len(sim) == 24
    assert all(s["cost"] >= 0 for s in sim)
    # Cheapest start should be in the overnight cheap block (0-6 @ $0.08).
    cheapest = min(sim, key=lambda s: s["cost"])
    assert 0 <= cheapest["start_hour"] < 6


def test_compute_estimate_includes_simulation():
    appl = {"label": "EV", "watts": 7200, "default_hours": 4.0}
    demand = {"curve": [0.5] * 24, "source": "mock"}
    r = compute_estimate(TOU, appl, 2.0, demand, now=datetime(2026, 1, 1, 16, 0))
    a = r["appliance"]
    assert len(a["simulation"]) == 24
    assert len(a["sim_costs"]) == 24
    assert a["sim_priciest_cost"] >= a["sim_cheapest_cost"]
    assert a["sim_max_savings"] >= 0
