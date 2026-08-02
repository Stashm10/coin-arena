from arena.flow.hawkes import MIN_FIT_EVENTS, simulate_hawkes
from arena.flow.signal import (COOLING, DISCONNECTED, EXIT, HEATING,
                               SENSITIVITIES, WARMUP, SignalEngine)


def _steady_points(n=60, price=1.0):
    return [(float(i), price) for i in range(n)]


def _rising_points(n=60):
    return [(float(i), 1.0 + 0.05 * i) for i in range(n)]


def _collapsing_points(n=25, price=10.0):
    return [(float(i), price * (0.9 ** i)) for i in range(n)]


def test_warmup_below_minimum_events():
    eng = SignalEngine()
    state = eng.update(now=10.0, times=[float(i) for i in range(5)],
                       price_points=_rising_points(), hazard_ps=0.0)
    assert state.state == WARMUP
    assert state.eta is None


def test_disconnected_suppresses_all_numbers():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    eng.update(now=times[-1], times=times, price_points=_rising_points(),
               hazard_ps=0.0)
    state = eng.mark_disconnected()
    assert state.state == DISCONNECTED
    assert state.eta is None and state.lam is None and state.hold_drift is None


def test_reconnect_returns_to_warmup_until_window_refills():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    eng.update(now=times[-1], times=times, price_points=_rising_points(),
               hazard_ps=0.0)
    eng.mark_disconnected()
    eng.mark_reconnected()
    state = eng.update(now=0.0, times=[0.0, 1.0], price_points=_rising_points(),
                       hazard_ps=0.0)
    assert state.state == WARMUP


def test_hazard_above_drift_fires_exit_immediately():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    assert len(times) >= MIN_FIT_EVENTS
    state = eng.update(now=times[-1], times=times,
                       price_points=_steady_points(),  # zero drift
                       hazard_ps=0.01)                 # any hazard beats it
    assert state.state == EXIT
    assert state.reason == "hazard exceeds drift"


def test_healthy_rising_coin_does_not_fire():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.8, 2.0, 200.0, seed=5)
    state = eng.update(now=times[-1], times=times,
                       price_points=_rising_points(), hazard_ps=1e-9)
    assert state.state in (HEATING, COOLING)
    assert state.state != EXIT


def test_momentary_dip_does_not_fire_before_persistence_elapses():
    eng = SignalEngine(sensitivity="late")  # persist_s = 10
    hot = simulate_hawkes(1.0, 1.9, 2.0, 200.0, seed=5)
    eng.update(now=hot[-1], times=hot, price_points=_rising_points(),
               hazard_ps=1e-9)
    quiet = hot[:MIN_FIT_EVENTS + 5]
    dipped = eng.update(now=hot[-1] + 1.0, times=quiet,
                        price_points=_rising_points(), hazard_ps=1e-9)
    assert dipped.state != EXIT  # 1s < 10s persistence
    recovered = eng.update(now=hot[-1] + 2.0, times=hot,
                           price_points=_rising_points(), hazard_ps=1e-9)
    assert recovered.state != EXIT


def test_exit_latches_once_fired():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    eng.update(now=times[-1], times=times, price_points=_steady_points(),
               hazard_ps=0.01)
    later = eng.update(now=times[-1] + 5.0, times=times,
                       price_points=_rising_points(), hazard_ps=1e-12)
    assert later.state == EXIT


def test_sensitivity_presets_are_ordered():
    early, balanced, late = (SENSITIVITIES["early"], SENSITIVITIES["balanced"],
                             SENSITIVITIES["late"])
    assert early.c1 > balanced.c1 > late.c1
    assert early.persist_s < balanced.persist_s < late.persist_s


def test_exit_latch_survives_thin_window_after_crash():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    latched = eng.update(now=times[-1], times=times,
                         price_points=_steady_points(), hazard_ps=0.01)
    assert latched.state == EXIT
    assert latched.reason == "hazard exceeds drift"

    thin = times[:MIN_FIT_EVENTS - 5]  # trades dried up after the crash
    starved = eng.update(now=times[-1] + 1.0, times=thin,
                         price_points=_steady_points(), hazard_ps=0.01)
    assert starved.state == EXIT
    assert starved.reason == "hazard exceeds drift"

    refilled = eng.update(now=times[-1] + 2.0, times=times,
                          price_points=_steady_points(), hazard_ps=0.01)
    assert refilled.state == EXIT
    assert refilled.reason == "hazard exceeds drift"


def test_stopping_rule_fires_before_hawkes_warmup():
    # Only 25 trade events (< MIN_FIT_EVENTS=40) but the price has already
    # collapsed underneath -- signal 2 must not wait on signal 1's warmup.
    eng = SignalEngine()
    times = [float(i) for i in range(25)]
    state = eng.update(now=24.0, times=times,
                       price_points=_collapsing_points(), hazard_ps=0.001)
    assert state.state == EXIT
    assert state.reason == "hazard exceeds drift"


def test_warmup_below_fit_events_keeps_hold_drift_but_no_fit_numbers():
    # 25 events, healthy rising price: still WARMUP (no sell signal), but the
    # stopping-rule's hold_drift should be visible to the UI even though the
    # Hawkes fit genuinely doesn't exist yet.
    eng = SignalEngine()
    times = [float(i) for i in range(25)]
    state = eng.update(now=24.0, times=times,
                       price_points=_rising_points(), hazard_ps=1e-9)
    assert state.state == WARMUP
    assert state.hold_drift is not None
    assert state.eta is None
    assert state.lam is None


def test_disconnected_precedence_with_few_events_and_selling_read():
    # DISCONNECTED must win even when there are too few events for a Hawkes
    # fit AND the (unevaluated) stopping rule would have said sell.
    eng = SignalEngine()
    eng.mark_disconnected()
    times = [float(i) for i in range(25)]
    state = eng.update(now=24.0, times=times,
                       price_points=_collapsing_points(), hazard_ps=0.001)
    assert state.state == DISCONNECTED
    assert state.eta is None and state.lam is None and state.hold_drift is None


def test_disconnected_while_latched_still_suppresses_numbers():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    latched = eng.update(now=times[-1], times=times,
                         price_points=_steady_points(), hazard_ps=0.01)
    assert latched.state == EXIT

    state = eng.mark_disconnected()
    assert state.state == DISCONNECTED
    assert state.eta is None and state.lam is None and state.hold_drift is None
