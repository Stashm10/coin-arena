import math

from arena.flow.hazard import (MIN_PRICE_POINTS, estimate_drift, hazard_per_s,
                               stopping_read)


def _ramp(rate_per_s: float, n: int = 60, dt: float = 1.0):
    """Deterministic exponential price path with known log-drift."""
    return [(i * dt, math.exp(rate_per_s * i * dt)) for i in range(n)]


def test_returns_none_below_minimum_points():
    assert estimate_drift(_ramp(0.01, n=MIN_PRICE_POINTS - 1)) is None


def test_recovers_known_log_drift_from_clean_ramp():
    drift, sigma = estimate_drift(_ramp(0.01))
    assert abs(drift - 0.01) < 1e-9
    assert sigma >= 0.0


def test_negative_ramp_gives_negative_drift():
    drift, _ = estimate_drift(_ramp(-0.02))
    assert drift < 0


def test_hazard_converts_percent_per_hour_to_per_second():
    # 36%/hr with no multipliers
    assert abs(hazard_per_s(36.0, []) - 0.36 / 3600.0) < 1e-12


def test_hazard_multipliers_compound():
    base = hazard_per_s(10.0, [])
    scaled = hazard_per_s(10.0, [2.0, 1.5])
    assert abs(scaled - base * 3.0) < 1e-12


def test_sells_when_hazard_exceeds_drift():
    read = stopping_read(_ramp(0.001), hazard_ps=0.01)
    assert read.sell is True
    assert read.hold_drift < 0


def test_holds_when_drift_exceeds_hazard():
    read = stopping_read(_ramp(0.05), hazard_ps=0.01)
    assert read.sell is False
    assert read.hold_drift > 0


def test_stopping_read_none_without_enough_points():
    assert stopping_read(_ramp(0.01, n=5), hazard_ps=0.01) is None


def test_sigma_is_zero_on_a_perfectly_smooth_path():
    _, sigma = estimate_drift(_ramp(0.01))
    assert sigma < 1e-9
