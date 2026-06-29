"""Grid carbon-intensity model.

EIA's free fuel-type feed reports hourly generation by fuel (coal, gas, wind,
solar, nuclear, hydro, ...) per region. Weighting each fuel by its lifecycle
carbon intensity yields a real, hourly **grid carbon intensity** curve in
gCO2eq per kWh -- computed from the same API WattWise already uses.

That powers the differentiator: optimize a run for **cost, carbon, or a blend**
of the two (a small multi-objective optimization).

Carbon factors are lifecycle medians (gCO2eq/kWh), IPCC/NREL-style. Storage
(battery/pumped-hydro) is treated as ~0 direct emissions on discharge.
"""

from __future__ import annotations

# gCO2eq per kWh by EIA fuel-type code.
CARBON_FACTORS: dict[str, float] = {
    "COL": 1000.0,  # coal
    "NG": 450.0,    # natural gas
    "OIL": 900.0,   # petroleum
    "OTH": 700.0,   # other / unknown -> assume mostly fossil
    "BIO": 230.0,   # biomass
    "SUN": 45.0,    # solar (lifecycle)
    "GEO": 38.0,    # geothermal
    "WAT": 24.0,    # hydro
    "NUC": 12.0,    # nuclear
    "WND": 11.0,    # wind
    "BAT": 0.0,     # battery storage (no direct emissions on discharge)
    "PS": 0.0,      # pumped storage
}
_DEFAULT_FACTOR = 500.0  # unrecognized fuel codes


def carbon_intensity(mix: dict[str, float]) -> float | None:
    """Generation-weighted gCO2/kWh for one hour's fuel mix (MW by fuel)."""
    total = 0.0
    weighted = 0.0
    for fuel, mw in mix.items():
        if mw is None or mw <= 0:  # ignore charging/negatives and zeros
            continue
        factor = CARBON_FACTORS.get(fuel, _DEFAULT_FACTOR)
        total += mw
        weighted += mw * factor
    if total <= 0:
        return None
    return round(weighted / total, 1)


def carbon_intensity_curve(by_hour: dict[int, dict[str, float]]) -> list[float | None]:
    """24-slot carbon-intensity curve (gCO2/kWh) indexed by clock hour."""
    return [carbon_intensity(by_hour.get(h, {})) for h in range(24)]


def normalize(curve: list[float]) -> list[float]:
    """Min-max normalize a curve to 0..1 (flat -> all 0.5)."""
    lo, hi = min(curve), max(curve)
    if hi == lo:
        return [0.5] * len(curve)
    return [round((v - lo) / (hi - lo), 4) for v in curve]


def score_carbon(value: float, curve: list[float]) -> dict:
    """Green/Yellow/Red for carbon vs the day's range (lower = cleaner)."""
    lo, hi = min(curve), max(curve)
    if hi == lo:
        return {"level": "flat", "label": "Steady grid mix", "color": "slate"}
    rel = (value - lo) / (hi - lo)
    if rel <= 1 / 3:
        return {"level": "green", "label": "Clean grid right now", "color": "green"}
    if rel <= 2 / 3:
        return {"level": "yellow", "label": "Average grid mix", "color": "amber"}
    return {"level": "red", "label": "Dirty grid right now", "color": "red"}


def weighted_best_hour(
    price_curve: list[float], carbon_curve: list[float], carbon_weight: float
) -> int:
    """Hour minimizing a blend of normalized price and carbon.

    ``carbon_weight`` in [0, 1]: 0 = pure cost, 1 = pure carbon. Returns the
    best clock hour. This is the multi-objective core, exposed so the server
    and tests agree with the client-side slider math.
    """
    w = max(0.0, min(1.0, carbon_weight))
    npr = normalize(price_curve)
    nca = normalize(carbon_curve)
    blended = [(1 - w) * npr[h] + w * nca[h] for h in range(24)]
    return min(range(24), key=lambda h: blended[h])
