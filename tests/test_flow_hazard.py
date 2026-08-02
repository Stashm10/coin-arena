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


def test_drift_unbiased_when_a_bad_price_tick_is_filtered_out():
    # A non-positive price tick spliced into an otherwise clean ramp drops
    # both pairs touching it, but must not bias the recovered rate: the
    # denominator should track only the time actually covered by the
    # retained returns, not the raw first-to-last window span.
    clean = _ramp(0.01)
    dirty = clean[:30] + [(29.5, -1.0)] + clean[30:]
    clean_drift, _ = estimate_drift(clean)
    dirty_drift, _ = estimate_drift(dirty)
    assert abs(dirty_drift - clean_drift) < 1e-9


def test_drift_unbiased_when_a_non_increasing_timestamp_pair_is_filtered():
    # A duplicated (t, price) tick creates a zero/negative-dt pair that must
    # be dropped without corrupting the rest of the estimate.
    clean = _ramp(0.01)
    dirty = clean[:30] + [clean[29]] + clean[30:]
    clean_drift, _ = estimate_drift(clean)
    dirty_drift, _ = estimate_drift(dirty)
    assert abs(dirty_drift - clean_drift) < 1e-9


def test_none_when_filtering_leaves_fewer_than_two_usable_returns():
    # Nearly all points share one timestamp (filtered as non-increasing);
    # only the final pair is usable, which is below the len(rets) >= 2 floor.
    points = [(0.0, 1.0)] * (MIN_PRICE_POINTS - 1) + [(1.0, math.e)]
    assert estimate_drift(points) is None
