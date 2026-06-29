"""Pricing logic: base tariff, dynamic grid-aware price, forecast, windows.

Pure functions, no I/O -- easy to test, easy to reason about. The dynamic and
forecast curves come from combining the utility's base tariff (``build_price_curve``)
with a live grid-stress signal via :mod:`app.grid`.
"""

from __future__ import annotations

from datetime import datetime

from . import grid
from .data.appliances import run_energy_kwh


def price_at_hour(utility: dict, hour: int) -> float:
    """$/kWh for a given clock hour (0-23) for this utility (base tariff)."""
    if utility["structure"] == "flat":
        return float(utility["flat_rate"])
    for start, end, rate in utility["periods"]:
        if start <= hour < end:
            return float(rate)
    # Defensive fallback (periods should cover 0-24 with no gaps).
    return float(utility["periods"][-1][2])


def build_price_curve(utility: dict) -> list[float]:
    """24 base-tariff prices, one per clock hour."""
    return [price_at_hour(utility, h) for h in range(24)]


def appliance_cost(watts: int, hours: float, price_per_kwh: float) -> float:
    """Naive dollar cost = kW * hours * $/kWh (no duty cycle)."""
    kwh = (watts / 1000.0) * hours
    return round(kwh * price_per_kwh, 2)


def run_cost(appliance: dict, hours: float, price_per_kwh: float) -> float:
    """Physics-aware dollar cost using effective kWh (duty cycle + surge)."""
    return round(run_energy_kwh(appliance, hours) * price_per_kwh, 2)


def score_now(current_price: float, curve: list[float]) -> dict:
    """Classify current price vs the day's range -> green/yellow/red.

    Bottom third of range = green, top third = red. Flat-rate utilities (no
    spread) report 'flat'.
    """
    lo, hi = min(curve), max(curve)
    if hi == lo:
        return {
            "level": "flat",
            "label": "Flat rate -- same price all day",
            "color": "slate",
        }
    rel = (current_price - lo) / (hi - lo)
    if rel <= 1 / 3:
        return {"level": "green", "label": "Cheap right now", "color": "green"}
    if rel <= 2 / 3:
        return {"level": "yellow", "label": "Average right now", "color": "amber"}
    return {"level": "red", "label": "Expensive right now", "color": "red"}


def window_avg_price(curve: list[float], start_hour: int, n: int) -> float:
    """Average $/kWh for an `n`-hour window starting at `start_hour` (wraps)."""
    hours = [(start_hour + i) % 24 for i in range(n)]
    return sum(curve[h] for h in hours) / n


def best_window(curve: list[float], duration_hours: float, from_hour: int) -> dict:
    """Cheapest consecutive window of length `duration_hours` in next 24h."""
    n = max(1, round(duration_hours))
    best = None
    for offset in range(24):
        start = from_hour + offset
        if offset + n > 24:  # window must fit fully in the 24h horizon
            break
        avg = window_avg_price(curve, start, n)
        if best is None or avg < best["avg_price"]:
            best = {
                "start_hour": start % 24,
                "end_hour": (start + n) % 24,
                "avg_price": round(avg, 4),
                "length_hours": n,
            }
    return best


def fmt_hour(hour: int) -> str:
    """12-hour clock label, e.g. 0 -> '12 AM', 16 -> '4 PM'."""
    hour %= 24
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{h12} {suffix}"


def simulate_by_start_hour(
    curve: list[float], appliance: dict, hours: float
) -> list[dict]:
    """Physics-aware cost of a run for every possible start hour (0-23).

    Wraps past midnight, so it answers "what would it cost started at 2 PM vs
    2 AM?" for all 24 start hours. Powers the cost simulator.
    """
    n = max(1, round(hours))
    out: list[dict] = []
    for start in range(24):
        avg = window_avg_price(curve, start, n)
        out.append(
            {
                "start_hour": start,
                "label": fmt_hour(start),
                "avg_price": round(avg, 4),
                "cost": run_cost(appliance, hours, avg),
            }
        )
    return out


def compute_estimate(
    utility: dict,
    appliance: dict | None,
    hours: float,
    signal: dict,
    now: datetime | None = None,
) -> dict:
    """Tie it together: base tariff + live grid signal -> full result payload.

    ``signal`` is the dict from :func:`app.eia.get_grid_signal`
    (``{"stress", "forecast", "source"}``).
    """
    now = now or datetime.now()
    current_hour = now.hour

    base_curve = build_price_curve(utility)
    stress = signal["stress"]
    forecast_stress = signal.get("forecast", stress)
    source = signal["source"]

    dynamic_curve = grid.apply_dynamic(base_curve, stress)
    forecast_curve = grid.apply_dynamic(base_curve, forecast_stress)

    base_price = base_curve[current_hour]
    current_price = dynamic_curve[current_hour]
    score = score_now(current_price, dynamic_curve)
    explanation = grid.explain(base_price, current_price, stress[current_hour], source)

    result: dict = {
        "current_hour": current_hour,
        "current_hour_label": fmt_hour(current_hour),
        "current_price": current_price,
        "base_price": base_price,
        "curve": dynamic_curve,
        "base_curve": base_curve,
        "forecast_curve": forecast_curve,
        "stress_curve": stress,
        "hour_labels": [fmt_hour(h) for h in range(24)],
        "grid_source": source,
        "explanation": explanation,
        "score": score,
        "structure": utility["structure"],
        "utility_name": utility["name"],
        "min_price": min(dynamic_curve),
        "max_price": max(dynamic_curve),
    }

    if appliance is not None:
        # Forward-looking: optimize against the day-ahead forecast curve.
        energy_kwh = run_energy_kwh(appliance, hours)
        cost_now = run_cost(appliance, hours, current_price)
        win = best_window(forecast_curve, hours, current_hour)
        cost_best = run_cost(appliance, hours, win["avg_price"])
        savings = round(cost_now - cost_best, 2)
        sim = simulate_by_start_hour(forecast_curve, appliance, hours)
        sim_costs = [s["cost"] for s in sim]
        cheapest = min(sim, key=lambda s: s["cost"])
        priciest = max(sim, key=lambda s: s["cost"])
        result["appliance"] = {
            "label": appliance["label"],
            "watts": appliance["watts"],
            "duty_cycle": appliance.get("duty_cycle", 1.0),
            "energy_kwh": energy_kwh,
            "hours": hours,
            "cost_now": cost_now,
            "best_window": win,
            "best_window_label": (
                f"{fmt_hour(win['start_hour'])} - {fmt_hour(win['end_hour'])}"
            ),
            "cost_best": cost_best,
            "savings": max(savings, 0.0),
            "run_now_is_best": win["start_hour"] == current_hour,
            "simulation": sim,
            "sim_costs": sim_costs,
            "sim_cheapest_hour": cheapest["start_hour"],
            "sim_cheapest_cost": cheapest["cost"],
            "sim_priciest_cost": priciest["cost"],
            "sim_max_savings": round(priciest["cost"] - cheapest["cost"], 2),
        }
    return result
