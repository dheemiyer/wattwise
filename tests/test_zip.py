"""Tests for zip resolution: curated metros + nationwide state fallback."""

from app.data.states import prefix_state
from app.data.zip_lookup import lookup_by_zip


def test_prefix_state_known():
    assert prefix_state("238") == "VA"   # Chesterfield, VA
    assert prefix_state("432") == "OH"   # Columbus, OH
    assert prefix_state("750") == "TX"
    assert prefix_state("900") == "CA"


def test_prefix_state_invalid():
    assert prefix_state("ab1") is None
    assert prefix_state("99") is None


def test_curated_metro_is_high_confidence():
    m = lookup_by_zip("75001")  # Dallas / Oncor
    assert m["confidence"] == "high"
    assert m["default_utility"] == "oncor"


def test_state_fallback_columbus():
    m = lookup_by_zip("43210")  # Columbus, OH -- not curated
    assert m is not None
    assert m["confidence"] == "state"
    assert m["state"] == "OH"
    assert m["default_utility"] == "aep_ohio"


def test_state_fallback_chesterfield():
    m = lookup_by_zip("23832")  # Chesterfield, VA -- not curated
    assert m is not None
    assert m["confidence"] == "state"
    assert m["state"] == "VA"


def test_invalid_zip_is_none():
    assert lookup_by_zip("") is None
    assert lookup_by_zip("ab") is None


def test_nationwide_coverage_no_gaps():
    # Every plausible populated prefix should resolve to *something*.
    resolved = sum(1 for n in range(1000) if lookup_by_zip(f"{n:03d}00"))
    assert resolved > 800  # ~900 valid US prefixes; allow for unassigned ranges
