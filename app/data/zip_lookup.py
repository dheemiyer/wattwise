"""Curated zip-prefix -> utility -> rate structure lookup.

Real OpenEI integration is a future swap-in. For now this covers major US
metros with representative rate structures so the app delivers value on day
one. Maps by 3-digit zip prefix (ZCTA-ish) which is plenty for region/utility
resolution.

Rate structures
---------------
- "tou"  : time-of-use. `periods` is a list of (start_hour, end_hour, $/kWh)
           covering 0-24 with no gaps. Hours are local clock hours.
- "flat" : single price all day via `flat_rate`.

`eia_region` is the EIA-930 balancing-authority/region code used to pull live
grid demand as a "grid stress" overlay.
"""

# --- Utility definitions (the source of truth for pricing) ------------------
UTILITIES: dict[str, dict] = {
    "oncor": {
        "name": "Oncor (TX)",
        "eia_region": "ERCO",
        "structure": "tou",
        "periods": [
            (0, 6, 0.08),    # overnight - cheap
            (6, 14, 0.14),   # morning/midday - shoulder
            (14, 20, 0.24),  # afternoon/evening - PEAK
            (20, 24, 0.12),  # late evening - shoulder
        ],
    },
    "centerpoint": {
        "name": "CenterPoint Energy (Houston)",
        "eia_region": "ERCO",
        "structure": "tou",
        "periods": [
            (0, 6, 0.09),
            (6, 15, 0.15),
            (15, 21, 0.26),
            (21, 24, 0.13),
        ],
    },
    "pge": {
        "name": "Pacific Gas & Electric (PG&E)",
        "eia_region": "CISO",
        "structure": "tou",
        "periods": [
            (0, 15, 0.30),   # off-peak
            (15, 16, 0.40),  # partial-peak ramp
            (16, 21, 0.52),  # PEAK (CA evening duck curve)
            (21, 24, 0.40),  # partial-peak
        ],
    },
    "sce": {
        "name": "Southern California Edison",
        "eia_region": "CISO",
        "structure": "tou",
        "periods": [
            (0, 16, 0.28),
            (16, 21, 0.48),
            (21, 24, 0.34),
        ],
    },
    "coned": {
        "name": "Con Edison (NYC)",
        "eia_region": "NYIS",
        "structure": "tou",
        "periods": [
            (0, 8, 0.18),
            (8, 12, 0.26),
            (12, 20, 0.34),  # PEAK
            (20, 24, 0.22),
        ],
    },
    "comed": {
        "name": "ComEd (Chicago)",
        "eia_region": "PJM",
        "structure": "flat",
        "flat_rate": 0.16,
    },
    "georgia_power": {
        "name": "Georgia Power",
        "eia_region": "SOCO",
        "structure": "flat",
        "flat_rate": 0.14,
    },
    "xcel_co": {
        "name": "Xcel Energy (Colorado)",
        "eia_region": "PSCO",
        "structure": "tou",
        "periods": [
            (0, 13, 0.13),
            (13, 19, 0.28),  # PEAK
            (19, 24, 0.18),
        ],
    },
    "xcel_mn": {
        "name": "Xcel Energy (Minnesota)",
        "eia_region": "MISO",
        "structure": "flat",
        "flat_rate": 0.15,
    },
    "srp": {
        "name": "Salt River Project (Phoenix)",
        "eia_region": "AZPS",
        "structure": "tou",
        "periods": [
            (0, 14, 0.11),
            (14, 20, 0.29),  # PEAK (desert AC load)
            (20, 24, 0.14),
        ],
    },
}

# --- Zip prefix -> list of candidate utility keys ---------------------------
# First entry is the default; others are offered as alternates.
ZIP_PREFIX_TO_UTILITIES: dict[str, list[str]] = {
    "750": ["oncor"], "751": ["oncor"], "752": ["oncor"], "753": ["oncor"],
    "760": ["oncor"], "761": ["oncor"],
    "770": ["centerpoint"], "771": ["centerpoint"], "772": ["centerpoint"],
    "773": ["centerpoint"], "774": ["centerpoint"], "775": ["centerpoint"],
    "940": ["pge"], "941": ["pge"], "942": ["pge"], "943": ["pge"],
    "944": ["pge"], "945": ["pge"], "946": ["pge"], "950": ["pge"], "951": ["pge"],
    "900": ["sce"], "901": ["sce"], "902": ["sce"], "903": ["sce"],
    "904": ["sce"], "905": ["sce"], "906": ["sce"], "907": ["sce"], "917": ["sce"],
    "100": ["coned"], "101": ["coned"], "102": ["coned"], "103": ["coned"],
    "104": ["coned"], "111": ["coned"], "112": ["coned"], "113": ["coned"],
    "606": ["comed"], "607": ["comed"], "608": ["comed"], "601": ["comed"],
    "300": ["georgia_power"], "301": ["georgia_power"], "303": ["georgia_power"],
    "800": ["xcel_co"], "801": ["xcel_co"], "802": ["xcel_co"], "803": ["xcel_co"],
    "550": ["xcel_mn"], "551": ["xcel_mn"], "553": ["xcel_mn"], "554": ["xcel_mn"],
    "850": ["srp"], "852": ["srp"], "853": ["srp"],
}


def lookup_by_zip(zip_code: str) -> dict | None:
    """Resolve a 5-digit zip to region + candidate utilities.

    Returns a dict with `prefix`, `default_utility` (key), and `candidates`
    (list of {key, name}). Returns None if the prefix isn't covered.
    """
    zip_code = (zip_code or "").strip()
    if len(zip_code) < 3 or not zip_code[:3].isdigit():
        return None
    prefix = zip_code[:3]
    keys = ZIP_PREFIX_TO_UTILITIES.get(prefix)
    if not keys:
        return None
    return {
        "prefix": prefix,
        "default_utility": keys[0],
        "candidates": [{"key": k, "name": UTILITIES[k]["name"]} for k in keys],
    }


def get_utility(key: str) -> dict | None:
    """Return a utility config (with its key injected) or None."""
    util = UTILITIES.get(key)
    if util is None:
        return None
    return {"key": key, **util}


def covered_prefixes() -> list[str]:
    """All supported zip prefixes (for the 'where do we work' hint)."""
    return sorted(ZIP_PREFIX_TO_UTILITIES.keys())
