"""Dynamic, grid-aware pricing model.

Retail tariffs are static by design (a TOU plan's peak rate is fixed by the
utility). But the *real-time* cost of electricity on the wholesale grid swings
with demand -- and real-time-pricing (RTP) customers feel it directly. This
module models that effect honestly:

    effective price(hour) = base tariff(hour) x stress_multiplier(grid demand)

where ``base tariff`` is the utility's published schedule (real, contractual)
and ``stress_multiplier`` is derived from **live EIA grid demand** (real,
measured). The product is clearly labeled in the UI as a *modeled* dynamic
price -- never presented as a literal billed rate.

The same model applied to EIA's **day-ahead demand forecast** yields a genuine
next-24h price forecast.
"""

from __future__ import annotations

# Multiplier band: a fully-relaxed grid discounts the base rate; a maxed-out
# grid marks it up. ~+/-30% is a conservative, defensible RTP-style swing.
_MULT_LOW = 0.80
_MULT_HIGH = 1.35


def stress_multiplier(stress: float) -> float:
    """Map a 0..1 grid-stress value to a price multiplier in [LOW, HIGH]."""
    stress = max(0.0, min(1.0, stress))
    return round(_MULT_LOW + (_MULT_HIGH - _MULT_LOW) * stress, 4)


def apply_dynamic(base_curve: list[float], stress_curve: list[float]) -> list[float]:
    """Combine a 24h base tariff with a 24h stress signal -> dynamic prices."""
    return [
        round(base_curve[h] * stress_multiplier(stress_curve[h]), 4)
        for h in range(24)
    ]


def stress_label(stress: float) -> str:
    """Human description of the grid-stress level at an hour."""
    if stress <= 1 / 3:
        return "low grid demand"
    if stress <= 2 / 3:
        return "moderate grid demand"
    return "high grid demand"


def explain(base_price: float, dynamic_price: float, stress: float, source: str) -> str:
    """One-line 'why is it this price right now' explanation."""
    measured = "live EIA grid data" if source == "eia" else "a modeled grid curve"
    delta = dynamic_price - base_price
    if delta > 0.005:
        direction = (
            f"above the ${base_price:.3f} base rate because the grid is under "
            f"{stress_label(stress)}"
        )
    elif delta < -0.005:
        direction = (
            f"below the ${base_price:.3f} base rate thanks to {stress_label(stress)}"
        )
    else:
        direction = f"right at the ${base_price:.3f} base rate"
    return f"Effective price is {direction} (per {measured})."
