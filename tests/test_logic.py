"""Tests for the pure pricing logic -- no I/O, fast."""

from datetime import datetime

from app.grid import apply_dynamic, stress_multiplier
from app.data.appliances import run_energy_kwh
from app.logic import (
    appliance_cost,
    best_window,
    build_price_curve,
    compute_estimate,
    fmt_hour,
    price_at_hour,
    run_cost,
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
EV = {"label": "EV", "watts": 7200, "duty_cycle": 1.0, "startup_surge_kwh": 0.0}
AC = {"label": "AC", "watts": 3500, "duty_cycle": 0.6, "startup_surge_kwh": 0.05}

# Flat grid signal -> uniform multiplier, so the price *shape* is preserved.
SIGNAL_FLAT = {"stress": [0.5] * 24, "forecast": [0.5] * 24, "source": "mock"}


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


def test_run_energy_kwh_duty_cycle():
    # EV: continuous 7.2kW * 2h = 14.4 kWh
    assert run_energy_kwh(EV, 2) == 14.4
    # AC: 3.5kW * 2h * 0.6 duty + 0.05 surge = 4.2 + 0.05 = 4.25 kWh
    assert run_energy_kwh(AC, 2) == 4.25


def test_run_cost_uses_physics():
    # AC effective 4.25 kWh at $0.10 = $0.43 (rounded), not naive $0.70
    assert run_cost(AC, 2, 0.10) == 0.43


def test_stress_multiplier_bounds():
    assert stress_multiplier(0.0) == 0.80
    assert stress_multiplier(1.0) == 1.35
    assert 0.80 < stress_multiplier(0.5) < 1.35


def test_apply_dynamic_preserves_shape_when_flat_stress():
    base = build_price_curve(TOU)
    dyn = apply_dynamic(base, [0.5] * 24)
    # Uniform stress scales every hour identically -> cheapest stays cheapest.
    assert dyn.index(min(dyn)) == base.index(min(base))


def test_score_now_buckets():
    curve = build_price_curve(TOU)
    assert score_now(0.08, curve)["level"] == "green"
    assert score_now(0.24, curve)["level"] == "red"


def test_score_now_flat():
    curve = build_price_curve(FLAT)
    assert score_now(0.16, curve)["level"] == "flat"


def test_window_avg_price_wraps():
    curve = build_price_curve(TOU)
    # 23:00 ($0.12) + 00:00 ($0.08) avg = 0.10
    assert window_avg_price(curve, 23, 2) == 0.10


def test_best_window_finds_cheapest():
    curve = build_price_curve(TOU)
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


def test_simulate_by_start_hour_shape():
    curve = build_price_curve(TOU)
    sim = simulate_by_start_hour(curve, EV, 2.0)
    assert len(sim) == 24
    assert all(s["cost"] >= 0 for s in sim)
    cheapest = min(sim, key=lambda s: s["cost"])
    assert 0 <= cheapest["start_hour"] < 6  # overnight cheap block


def test_compute_estimate_with_appliance():
    now = datetime(2026, 1, 1, 16, 0)  # 4pm peak
    r = compute_estimate(TOU, EV, 2.0, SIGNAL_FLAT, now=now)
    assert r["base_price"] == 0.24
    # Dynamic price = base * multiplier(0.5) > base
    assert r["current_price"] > r["base_price"]
    assert r["appliance"]["cost_now"] > r["appliance"]["cost_best"]
    assert r["appliance"]["savings"] > 0
    assert r["score"]["level"] == "red"
    assert len(r["appliance"]["simulation"]) == 24


def test_compute_estimate_no_appliance():
    r = compute_estimate(TOU, None, 1.0, SIGNAL_FLAT, now=datetime(2026, 1, 1, 3, 0))
    assert "appliance" not in r
    assert r["base_price"] == 0.08
    assert "explanation" in r
    assert len(r["forecast_curve"]) == 24


def test_compute_estimate_includes_simulation():
    r = compute_estimate(TOU, AC, 2.0, SIGNAL_FLAT, now=datetime(2026, 1, 1, 16, 0))
    a = r["appliance"]
    assert len(a["sim_costs"]) == 24
    assert a["sim_priciest_cost"] >= a["sim_cheapest_cost"]
    assert a["sim_max_savings"] >= 0
    assert a["energy_kwh"] == run_energy_kwh(AC, 2.0)
