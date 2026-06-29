"""EIA-930 grid client: live hourly demand + day-ahead forecast.

EIA's free v2 API exposes hourly grid **demand** (type ``D``, actuals) and a
**day-ahead demand forecast** (type ``DF``) per balancing authority. Neither is
a retail price -- so we use them as a live *grid-stress* signal that drives the
dynamic pricing model in ``grid.py``.

Two real signals are returned:
- ``stress``   : today's normalized demand shape (actuals where available).
- ``forecast`` : the next-24h normalized forecast shape (genuine EIA forecast).

Network notes
-------------
This client is **proxy-aware**: set ``EIA_PROXY`` (or standard ``HTTPS_PROXY``)
and requests route through it -- required behind corporate networks where
``api.eia.gov`` isn't directly reachable. Without a key (or on any failure) we
fall back to a realistic synthesized curve and report ``source="mock"`` so the
UI stays honest about what's measured vs modeled.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import httpx

from . import cache

_EIA_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
_CACHE_TTL = 60 * 60  # 1 hour -- demand/forecast don't move minute-to-minute


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


def _normalize(values: list[float | None]) -> list[float] | None:
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


def _parse_by_hour(rows: list[dict]) -> list[float | None]:
    """Map EIA rows -> 24-slot list indexed by clock hour (latest wins)."""
    slots: list[float | None] = [None] * 24
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
    """Fetch one EIA series (``D`` or ``DF``) and return a normalized curve."""
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
    ``source`` is ``"eia"`` when at least one real series was fetched, else
    ``"mock"``.
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
