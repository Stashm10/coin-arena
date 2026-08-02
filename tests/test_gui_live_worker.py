from arena.flow.signal import DISCONNECTED, EXIT, WARMUP
from arena.gui.live_worker import WatchHandle, start_watch
from arena.stream.tape import TapeEvent


def test_handle_stop_sets_the_flag():
    handle = WatchHandle()
    assert handle.is_set() is False
    handle.stop()
    assert handle.is_set() is True


def _fake_watch(events, disconnect=False):
    async def watch_fn(key, mint, on_event, on_disconnect, on_reconnect, stop,
                       **kw):
        for e in events:
            on_event(e)
        if disconnect:
            on_disconnect()
    return watch_fn


def test_emits_warmup_for_a_thin_tape():
    states = []
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=states.append,
        watch_fn=_fake_watch([TapeEvent(ts=float(i), is_buy=True, sol=0.1,
                                        price=1.0) for i in range(5)]),
        clock=lambda: next(ticks))
    handle.join(timeout=5)
    assert states
    assert states[-1].state == WARMUP


def test_disconnect_emits_disconnected_with_no_numbers():
    states = []
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=states.append, watch_fn=_fake_watch([], disconnect=True),
        clock=lambda: next(ticks))
    handle.join(timeout=5)
    assert states[-1].state == DISCONNECTED
    assert states[-1].eta is None and states[-1].lam is None


def test_alert_fires_once_per_exit_latch(monkeypatch):
    import arena.gui.live_worker as worker_mod
    fired = []
    monkeypatch.setattr(worker_mod, "fire_alert",
                        lambda title, body: fired.append((title, body)))
    # Flat price + large assumed hazard forces the stopping rule to fire.
    # The clock advances 0.2s per event so a refit happens every 5th event
    # (QME_REFIT_INTERVAL_S = 1.0) — about 9 fits, not one per event.
    events = [TapeEvent(ts=i * 0.1, is_buy=True, sol=0.1, price=1.0)
              for i in range(45)]
    ticks = iter([i * 0.2 for i in range(400)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="early", base_hazard_pct=9000.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks))
    handle.join(timeout=10)
    assert len(fired) == 1
    assert fired[0][0] == "EXIT"
