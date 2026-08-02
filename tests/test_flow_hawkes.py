import math

from arena.flow.hawkes import (MIN_FIT_EVENTS, fit_hawkes, intensity,
                               log_likelihood, simulate_hawkes)


def test_returns_none_below_minimum_events():
    assert fit_hawkes([float(i) for i in range(MIN_FIT_EVENTS - 1)]) is None


def test_recovers_known_branching_ratio_from_simulated_process():
    # eta = alpha/beta = 1.2/2.0 = 0.6
    times = simulate_hawkes(mu=0.5, alpha=1.2, beta=2.0, horizon=600.0, seed=7)
    assert len(times) > 200, "simulator produced too few events to fit"
    fit = fit_hawkes(times)
    assert fit is not None
    # MLE on a finite sample is noisy; assert the estimate lands in the right
    # neighbourhood, not on the nose.
    assert 0.35 < fit.eta < 0.85
    assert 0.2 < fit.mu < 1.2


def test_recovers_low_branching_ratio_as_lower_than_high_one():
    quiet = simulate_hawkes(mu=0.5, alpha=0.2, beta=2.0, horizon=600.0, seed=11)
    hot = simulate_hawkes(mu=0.5, alpha=1.6, beta=2.0, horizon=600.0, seed=11)
    quiet_fit, hot_fit = fit_hawkes(quiet), fit_hawkes(hot)
    assert quiet_fit is not None and hot_fit is not None
    assert quiet_fit.eta < hot_fit.eta


def test_log_likelihood_matches_naive_formula_on_small_input():
    times = [0.0, 1.0, 1.5, 4.0]
    mu, alpha, beta = 0.3, 0.8, 1.5
    horizon = times[-1]
    naive = 0.0
    for i, t in enumerate(times):
        lam = mu + sum(alpha * math.exp(-beta * (t - s)) for s in times[:i])
        naive += math.log(lam)
    naive -= mu * horizon
    naive -= (alpha / beta) * sum(1 - math.exp(-beta * (horizon - s)) for s in times)
    assert abs(log_likelihood(times, mu, alpha, beta) - naive) < 1e-9


def test_intensity_decays_after_last_event():
    times = [0.0, 1.0, 2.0]
    fit = type("F", (), {"mu": 0.1, "alpha": 1.0, "beta": 1.0})()
    near = intensity(times, 2.0, fit)
    far = intensity(times, 20.0, fit)
    assert near > far
    assert abs(far - 0.1) < 1e-6  # decays back to baseline mu


def test_simulator_is_deterministic_for_a_seed():
    a = simulate_hawkes(0.5, 1.0, 2.0, 100.0, seed=3)
    b = simulate_hawkes(0.5, 1.0, 2.0, 100.0, seed=3)
    assert a == b
