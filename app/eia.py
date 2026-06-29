"""EIA-930 grid client: live demand, day-ahead forecast, and fuel mix.

EIA's free v2 API exposes, per balancing authority:
- hourly grid **demand** (type ``D``) and a **day-ahead forecast** (type ``DF``)
  -- used as the grid-stress signal that drives dynamic pricing (``grid.py``).
- hourly **generation by fuel type** -- reduced to a real grid **carbon
  intensity** curve via ``carbon.py``.

Network notes
-------------
This client is **proxy-aware**: set ``EIA_PROXY`` (or standard ``HTTPS_PROXY``)
so requests route through it -- required behind corporate networks where
``api.eia.gov`` isn't directly reachable. Without a key (or on any failure) we
fall back to realistic synthesized curves and report ``source="mock"`` so the
UI stays honest about what's measured vs modeled.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import httpx

from . import cache
from .carbon import carbon_intensity_curve

_EIA_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
_FUEL_URL = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"
_CACHE_TTL = 60 * 60  # 1 hour -- these signals don't move minute-to-minute


def _api_key() -> str | None:
    key = os.getenv("EIA_API_KEY", "").strip()
    return key or None


def _proxy() -> str | None:
    for var in ("EIA_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.getenv(var, "").strip()
        if val:
            return val
    return None


def _client() -> httpx.Client:
    """Build an httpx client, honoring a proxy across httpx versions."""
    proxy = _proxy()
    if not proxy:
        return httpx.Client(timeout=12)
    try:  # httpx >= 0.26
        return httpx.Client(timeout=12, proxy=proxy)
    except TypeError:  # older httpx
        return httpx.Client(timeout=12, proxies=proxy)


def _mock_curve(shift: float = 0.0) -> list[float]:
    """A believable 24h demand shape normalized 0..1.

    Overnight trough, morning bump, broad evening peak. ``shift`` nudges the
    peak slightly so the 'forecast' curve isn't identical to today's actuals.
    """
    raw = []
    for h in range(24):
        morning = 0.25 * math.exp(-((h - 8) ** 2) / 8)
        evening = 0.6 * math.exp(-((h - (18 + shift)) ** 2) / 10)
        raw.append(0.35 + morning + evening)
    lo, hi = min(raw), max(raw)
    return [round((v - lo) / (hi - lo), 3) for v in raw]


def _mock_carbon_curve() -> list[float]:
    """Believable carbon curve (gCO2/kWh): cleaner midday (solar), dirty eve."""
    raw = []
    for h in range(24):
        solar_dip = 220 * math.exp(-((h - 13) ** 2) / 14)  # midday solar cleans
        evening_bump = 120 * math.exp(-((h - 19) ** 2) / 12)  # gas peakers
        raw.append(round(520 - solar_dip + evening_bump, 1))
    return raw


def _normalize(values: list) -> list | None:
    """Fill gaps with the mean, then min-max normalize to 0..1 over 24 slots."""
    known = [v for v in values if v is not None]
    if not known:
        return None
    fill = sum(known) / len(known)
    filled = [v if v is not None else fill for v in values]
    lo, hi = min(filled), max(filled)
    if hi == lo:
        return [0.5] * 24
    return [round((v - lo) / (hi - lo), 3) for v in filled]


def _parse_by_hour(rows: list) -> list:
    """Map EIA rows -> 24-slot list indexed by clock hour (latest wins)."""
    slots = [None] * 24
    for row in rows:
        period, value = row.get("period"), row.get("value")
        if period is None or value is None:
            continue
        try:
            slots[int(str(period)[11:13])] = float(value)
        except (ValueError, TypeError, IndexError):
            continue
    return slots


def _fetch(region: str, key: str, dtype: str, hours_back: int, hours_fwd: int):
    """Fetch one EIA demand series (``D`` or ``DF``); return normalized curve."""
    end = datetime.utcnow() + timedelta(hours=hours_fwd)
    start = end - timedelta(hours=hours_back + hours_fwd)
    params = {
        "api_key": key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": region,
        "facets[type][]": dtype,
        "start": start.strftime("%Y-%m-%dT%H"),
        "end": end.strftime("%Y-%m-%dT%H"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "72",
    }
    with _client() as client:
        resp = client.get(_EIA_URL, params=params)
        resp.raise_for_status()
        rows = resp.json().get("response", {}).get("data", [])
    return _normalize(_parse_by_hour(rows))


def get_grid_signal(region: str) -> dict:
    """Live grid-stress + forecast for a region (both normalized 0..1 by hour).

    Returns ``{"stress": [..24..], "forecast": [..24..], "source": str}``.
    """
    cache_key = f"grid:{region}:{datetime.utcnow():%Y-%m-%d-%H}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    key = _api_key()
    if key:
        try:
            stress = _fetch(region, key, "D", hours_back=36, hours_fwd=0)
            forecast = _fetch(region, key, "DF", hours_back=12, hours_fwd=24)
            if stress or forecast:
                payload = {
                    "stress": stress or forecast,
                    "forecast": forecast or stress,
                    "source": "eia",
                }
                cache.set(cache_key, payload, _CACHE_TTL)
                return payload
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # fall through to mock

    payload = {
        "stress": _mock_curve(),
        "forecast": _mock_curve(shift=0.5),
        "source": "mock",
    }
    cache.set(cache_key, payload, _CACHE_TTL)
    return payload


def _fetch_carbon(region: str, key: str):
    """Fetch recent hourly fuel mix -> 24h carbon-intensity curve (gCO2/kWh)."""
    end = datetime.utcnow() + timedelta(hours=1)
    start = end - timedelta(hours=48)
    params = {
        "api_key": key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": region,
        "start": start.strftime("%Y-%m-%dT%H"),
        "end": end.strftime("%Y-%m-%dT%H"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "5000",
    }
    with _client() as client:
        resp = client.get(_FUEL_URL, params=params)
        resp.raise_for_status()
        rows = resp.json().get("response", {}).get("data", [])

    by_hour: dict = {}
    seen: set = set()
    for row in rows:
        period, fuel, value = row.get("period"), row.get("fueltype"), row.get("value")
        if period is None or fuel is None or value is None:
            continue
        try:
            hour = int(str(period)[11:13])
            mw = float(value)
        except (ValueError, TypeError, IndexError):
            continue
        if (hour, fuel) in seen:  # rows newest-first; keep the latest per slot
            continue
        seen.add((hour, fuel))
        by_hour.setdefault(hour, {})[fuel] = mw

    if not by_hour:
        return None
    curve = carbon_intensity_curve(by_hour)
    known = [v for v in curve if v is not None]
    if not known:
        return None
    fill = sum(known) / len(known)
    return [round(v if v is not None else fill, 1) for v in curve]


def get_carbon_signal(region: str) -> dict:
    """Hourly grid carbon intensity (gCO2/kWh) for a region.

    Returns ``{"curve": [..24..], "source": "eia"|"mock"}`` -- computed from
    EIA's real hourly fuel-mix feed, with a modeled fallback.
    """
    cache_key = f"carbon:{region}:{datetime.utcnow():%Y-%m-%d-%H}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    key = _api_key()
    if key:
        try:
            curve = _fetch_carbon(region, key)
            if curve is not None:
                payload = {"curve": curve, "source": "eia"}
                cache.set(cache_key, payload, _CACHE_TTL)
                return payload
        except (httpx.HTTPError, ValueError, KeyError):
            pass

    payload = {"curve": _mock_carbon_curve(), "source": "mock"}
    cache.set(cache_key, payload, _CACHE_TTL)
    return payload
