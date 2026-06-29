"""Tests for the carbon-intensity model and multi-objective optimizer."""

from app.carbon import (
    carbon_intensity,
    carbon_intensity_curve,
    normalize,
    score_carbon,
    weighted_best_hour,
)


def test_carbon_intensity_clean_vs_dirty():
    clean = {"WND": 800, "SUN": 200, "NUC": 500}  # mostly renewables/nuclear
    dirty = {"COL": 800, "NG": 700}               # coal + gas
    assert carbon_intensity(clean) < carbon_intensity(dirty)


def test_carbon_intensity_ignores_negatives_and_zero():
    # Battery charging (negative) and zero solar at night are ignored.
    mix = {"NG": 1000, "BAT": -300, "SUN": 0}
    assert carbon_intensity(mix) == 450.0  # pure NG factor


def test_carbon_intensity_empty_is_none():
    assert carbon_intensity({}) is None
    assert carbon_intensity({"BAT": -50}) is None


def test_carbon_intensity_curve_fills_24():
    by_hour = {0: {"WND": 100}, 12: {"COL": 100}}
    curve = carbon_intensity_curve(by_hour)
    assert len(curve) == 24
    assert curve[0] == 11.0     # wind factor
    assert curve[12] == 1000.0  # coal factor
    assert curve[5] is None     # no data that hour


def test_normalize_flat():
    assert normalize([5, 5, 5]) == [0.5, 0.5, 0.5]


def test_score_carbon_buckets():
    curve = [100, 300, 500, 700, 900]
    assert score_carbon(100, curve)["level"] == "green"
    assert score_carbon(900, curve)["level"] == "red"


def test_weighted_best_hour_extremes():
    # Cheapest at hour 3, greenest at hour 20.
    price = [0.5] * 24
    price[3] = 0.01
    carbon = [500.0] * 24
    carbon[20] = 10.0
    assert weighted_best_hour(price, carbon, 0.0) == 3    # pure cost
    assert weighted_best_hour(price, carbon, 1.0) == 20   # pure carbon


def test_weighted_best_hour_clamps_weight():
    price = [float(h) for h in range(24)]      # cheapest at 0
    carbon = [float(24 - h) for h in range(24)]  # greenest at 23
    assert weighted_best_hour(price, carbon, -5) == 0   # clamped to pure cost
    assert weighted_best_hour(price, carbon, 9) == 23   # clamped to pure carbon
