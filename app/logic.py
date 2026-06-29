"""Pricing logic: price curve, cost calc, best-window, scoring.

Pure functions, no I/O -- easy to test, easy to reason about.
"""

from __future__ import annotations

from datetime import datetime


def price_at_hour(utility: dict, hour: int) -> float:
    """$/kWh for a given clock hour (0-23) for this utility."""
    if utility["structure"] == "flat":
        return float(utility["flat_rate"])
    for start, end, rate in utility["periods"]:
        if start <= hour < end:
            return float(rate)
    # Defensive fallback (periods should cover 0-24 with no gaps).
    return float(utility["periods"][-1][2])


def build_price_curve(utility: dict) -> list[float]:
    """24 prices, one per clock hour."""
    return [price_at_hour(utility, h) for h in range(24)]


def appliance_cost(watts: int, hours: float, price_per_kwh: float) -> float:
    """Dollar cost = kW * hours * $/kWh."""
    kwh = (watts / 1000.0) * hours
    return round(kwh * price_per_kwh, 2)


def score_now(current_price: float, curve: list[float]) -> dict:
    """Classify the current price vs today's range -> green/yellow/red.

    Thresholds are relative: bottom third of range = green, top third = red.
    For flat-rate utilities (no spread) everything is 'flat'.
    """
    lo, hi = min(curve), max(curve)
    if hi == lo:
        return {
            "level": "flat",
            "label": "Flat rate -- same price all day",
            "color": "slate",
        }
    span = hi - lo
    rel = (current_price - lo) / span
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
    """Cheapest consecutive window of length `duration_hours` in next 24h.

    Searches the next 24 hours starting at `from_hour` (wrapping past
    midnight). Returns the window start hour and its average price.
    """
    n = max(1, round(duration_hours))
    best = None
    for offset in range(24):
        start = from_hour + offset
        # Window must fit fully within the next 24h horizon.
        if offset + n > 24:
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


def simulate_by_start_hour(
    curve: list[float], watts: int, hours: float
) -> list[dict]:
    """Cost of running an appliance for every possible start hour (0-23).

    Each window wraps past midnight, so this answers "what would it cost if I
    started at 2 PM vs 2 AM?" for all 24 start hours. Powers the simulator.
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
                "cost": appliance_cost(watts, hours, avg),
            }
        )
    return out


def fmt_hour(hour: int) -> str:
    """12-hour clock label, e.g. 0 -> '12 AM', 16 -> '4 PM'."""
    hour %= 24
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{h12} {suffix}"


def compute_estimate(
    utility: dict,
    appliance: dict | None,
    hours: float,
    demand: dict,
    now: datetime | None = None,
) -> dict:
    """Tie it all together into one result payload for the template."""
    now = now or datetime.now()
    current_hour = now.hour
    curve = build_price_curve(utility)
    current_price = curve[current_hour]
    score = score_now(current_price, curve)

    result: dict = {
        "current_hour": current_hour,
        "current_hour_label": fmt_hour(current_hour),
        "current_price": current_price,
        "curve": curve,
        "hour_labels": [fmt_hour(h) for h in range(24)],
        "demand_curve": demand["curve"],
        "demand_source": demand["source"],
        "score": score,
        "structure": utility["structure"],
        "utility_name": utility["name"],
        "min_price": min(curve),
        "max_price": max(curve),
    }

    if appliance is not None:
        cost_now = appliance_cost(appliance["watts"], hours, current_price)
        win = best_window(curve, hours, current_hour)
        cost_best = appliance_cost(appliance["watts"], hours, win["avg_price"])
        savings = round(cost_now - cost_best, 2)
        sim = simulate_by_start_hour(curve, appliance["watts"], hours)
        sim_costs = [s["cost"] for s in sim]
        cheapest = min(sim, key=lambda s: s["cost"])
        priciest = max(sim, key=lambda s: s["cost"])
        result["appliance"] = {
            "label": appliance["label"],
            "watts": appliance["watts"],
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
