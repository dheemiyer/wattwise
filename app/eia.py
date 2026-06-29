"""EIA-930 hourly grid-demand client with graceful mock fallback.

EIA's free API exposes hourly grid *demand* (and day-ahead forecast) by
balancing authority -- not retail price. We use that as a live "grid stress"
overlay on top of the utility's published price schedule.

If `EIA_API_KEY` is unset (or the call fails), we synthesize a realistic
demand curve so the whole app still works end-to-end. The response always
reports `source` ("eia" or "mock") so the UI can be honest about it.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import httpx

from . import cache

_EIA_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
_CACHE_TTL = 60 * 60  # 1 hour -- demand forecast doesn't move minute-to-minute


def _api_key() -> str | None:
    key = os.getenv("EIA_API_KEY", "").strip()
    return key or None


def _mock_demand_curve() -> list[float]:
    """Synthesize a believable 24h demand shape, normalized to 0..1.

    Shape: trough overnight (~3-5am), morning ramp, broad afternoon/evening
    peak (~5-7pm). Deterministic so results are stable within the hour.
    """
    raw = []
    for h in range(24):
        # Two humps: small morning, large evening. Baseline + cosine terms.
        morning = 0.25 * math.exp(-((h - 8) ** 2) / 8)
        evening = 0.6 * math.exp(-((h - 18) ** 2) / 10)
        baseline = 0.35
        raw.append(baseline + morning + evening)
    lo, hi = min(raw), max(raw)
    return [round((v - lo) / (hi - lo), 3) for v in raw]


def _parse_eia(rows: list[dict]) -> dict[int, float] | None:
    """Map EIA rows -> {local_hour: value}. Returns None if unusable."""
    by_hour: dict[int, float] = {}
    for row in rows:
        period = row.get("period")  # e.g. "2024-06-29T14"
        value = row.get("value")
        if period is None or value is None:
            continue
        try:
            hour = int(str(period)[11:13])
            by_hour[hour] = float(value)
        except (ValueError, TypeError):
            continue
    return by_hour or None


def get_demand_curve(eia_region: str) -> dict:
    """Return a 24-element demand curve (index = clock hour) normalized 0..1.

    Output: {"curve": [..24..], "source": "eia"|"mock"}.
    """
    cache_key = f"demand:{eia_region}:{datetime.utcnow():%Y-%m-%d-%H}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    key = _api_key()
    if key:
        try:
            result = _fetch_eia(eia_region, key)
            if result is not None:
                payload = {"curve": result, "source": "eia"}
                cache.set(cache_key, payload, _CACHE_TTL)
                return payload
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # fall through to mock

    payload = {"curve": _mock_demand_curve(), "source": "mock"}
    cache.set(cache_key, payload, _CACHE_TTL)
    return payload


def _fetch_eia(eia_region: str, api_key: str) -> list[float] | None:
    """Hit EIA v2 for recent hourly demand forecast; normalize to 0..1."""
    end = datetime.utcnow() + timedelta(hours=1)
    start = end - timedelta(hours=48)
    params = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": eia_region,
        "facets[type][]": "DF",  # day-ahead demand forecast
        "start": start.strftime("%Y-%m-%dT%H"),
        "end": end.strftime("%Y-%m-%dT%H"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "48",
    }
    with httpx.Client(timeout=10) as client:
        resp = client.get(_EIA_URL, params=params)
        resp.raise_for_status()
        rows = resp.json().get("response", {}).get("data", [])
    by_hour = _parse_eia(rows)
    if not by_hour:
        return None
    # Build a 24-slot curve indexed by clock hour, filling gaps with neighbours.
    values = [by_hour.get(h) for h in range(24)]
    known = [v for v in values if v is not None]
    if not known:
        return None
    fill = sum(known) / len(known)
    values = [v if v is not None else fill for v in values]
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * 24
    return [round((v - lo) / (hi - lo), 3) for v in values]
