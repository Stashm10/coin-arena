from arena.flow.signal import DISCONNECTED, EXIT, WARMUP
from arena.gui.live_worker import WatchHandle, start_watch
from arena.stream.tape import TapeEvent
from arena.thresholds import QME_HAZARD_MULT_MINT_LIVE

# ARENA_DATA_DIR isolation (so start_watch's default recorder_factory never
# touches the user's real database) is provided repo-wide by the autouse
# fixture in tests/conftest.py.

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


def test_no_get_multipliers_matches_flat_base_hazard(monkeypatch):
    # Existing-behaviour guard: omitting get_multipliers must still behave
    # exactly like today's flat base hazard (no multipliers applied).
    import arena.gui.live_worker as worker_mod
    real_hazard_per_s = worker_mod.hazard_per_s
    seen: list[list[float]] = []

    def spy(base_pct, mults):
        seen.append(list(mults))
        return real_hazard_per_s(base_pct, mults)

    monkeypatch.setattr(worker_mod, "hazard_per_s", spy)
    events = [TapeEvent(ts=float(i), is_buy=True, sol=0.1, price=1.0)
              for i in range(10)]
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks))
    handle.join(timeout=5)
    assert seen  # hazard_per_s was actually invoked from evaluate
    assert all(m == [] for m in seen)


def test_toggle_changes_hazard_on_a_running_watch(monkeypatch):
    # The hazard multipliers must be recomputed per evaluation (not once at
    # start_watch time) so ticking a toggle takes effect without restarting
    # the watch.
    import arena.gui.live_worker as worker_mod
    real_hazard_per_s = worker_mod.hazard_per_s
    seen: list[float] = []

    def spy(base_pct, mults):
        rate = real_hazard_per_s(base_pct, mults)
        seen.append(rate)
        return rate

    monkeypatch.setattr(worker_mod, "hazard_per_s", spy)
    toggle = {"mults": []}

    def get_multipliers():
        # Flip the toggle on partway through the run to prove a later
        # evaluation picks up the change without a restart.
        if len(seen) >= 2:
            toggle["mults"] = [QME_HAZARD_MULT_MINT_LIVE]
        return toggle["mults"]

    events = [TapeEvent(ts=i * 0.5, is_buy=True, sol=0.1, price=1.0)
              for i in range(30)]
    ticks = iter([i * 0.5 for i in range(400)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks), get_multipliers=get_multipliers)
    handle.join(timeout=5)
    assert seen[0] == real_hazard_per_s(20.0, [])
    assert seen[-1] == real_hazard_per_s(20.0, [QME_HAZARD_MULT_MINT_LIVE])
    assert seen[-1] > seen[0]


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


class FakeRecorder:
    def __init__(self):
        self.started = False
        self.prices = []
        self.states = []
        self.hazards = []
        self.finished = False

    def start(self):
        self.started = True

    def note_price(self, price):
        self.prices.append(price)

    def note_state(self, state, hazard_ps=None):
        self.states.append(state.state)
        self.hazards.append(hazard_ps)

    def finish(self):
        self.finished = True


def test_recorder_is_started_on_the_worker_thread():
    rec = FakeRecorder()
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch([]),
        clock=lambda: next(ticks), recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert rec.started is True


def test_recorder_sees_every_trade_price():
    rec = FakeRecorder()
    events = [TapeEvent(ts=float(i), is_buy=True, sol=0.1, price=1.0 + i)
              for i in range(3)]
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks), recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert rec.prices == [1.0, 2.0, 3.0]


def test_recorder_sees_emitted_states():
    rec = FakeRecorder()
    events = [TapeEvent(ts=float(i), is_buy=True, sol=0.1, price=1.0)
              for i in range(5)]
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks), recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert "WARMUP" in rec.states


def test_recorder_sees_the_disconnected_state():
    rec = FakeRecorder()
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch([], disconnect=True),
        clock=lambda: next(ticks), recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert "DISCONNECTED" in rec.states


def test_a_raising_recorder_does_not_break_the_watch():
    """Telemetry must never take down a live watch."""
    class ExplodingRecorder:
        def start(self):
            raise RuntimeError("boom")

        def note_price(self, price):
            raise RuntimeError("boom")

        def note_state(self, state, hazard_ps=None):
            raise RuntimeError("boom")

        def finish(self):
            raise RuntimeError("boom")

    states = []
    events = [TapeEvent(ts=float(i), is_buy=True, sol=0.1, price=1.0)
              for i in range(3)]
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=states.append, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks), recorder_factory=ExplodingRecorder)
    handle.join(timeout=5)
    assert states, "the watch must keep emitting states despite recorder failure"


def test_finish_is_called_when_the_watch_completes_normally():
    """Finding 1: ended_ts must be written whether the watch ends normally
    or by exception, so worker() calls recorder.finish() in a finally
    around asyncio.run(run())."""
    rec = FakeRecorder()
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch([]),
        clock=lambda: next(ticks), recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert rec.finished is True


def test_finish_is_called_even_when_the_watch_raises():
    """If anything escapes the stream loop unhandled, the watch thread must
    not die silently: the engine's own contract (arena/flow/signal.py) is
    that an absence of trades IS the signal, so a dead socket must surface
    as DISCONNECTED (all numerics None) through on_state — never leave the
    UI readout frozen looking live — and the session must still get its
    ended_ts."""
    rec = FakeRecorder()
    states = []

    async def _raising_watch_fn(key, mint, on_event, on_disconnect,
                                on_reconnect, stop, **kw):
        raise RuntimeError("socket blew up")

    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=states.append, watch_fn=_raising_watch_fn,
        clock=lambda: 0.0, recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert rec.finished is True
    assert states, "a DISCONNECTED state must reach the UI when the watch crashes"
    last = states[-1]
    assert last.state == DISCONNECTED
    assert last.eta is None and last.eta_peak is None
    assert last.lam is None and last.lam_peak is None
    assert last.hold_drift is None


def test_recorder_receives_the_effective_hazard_per_evaluation():
    """Finding 2: get_multipliers() is re-read on every evaluation, so the
    recorded toggles snapshot alone cannot say what hazard produced a given
    signal row. evaluate() must pass its computed hazard into note_state."""
    from arena.flow.hazard import hazard_per_s as real_hazard_per_s

    rec = FakeRecorder()
    events = [TapeEvent(ts=float(i), is_buy=True, sol=0.1, price=1.0)
              for i in range(5)]
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks), recorder_factory=lambda: rec)
    handle.join(timeout=5)
    assert rec.hazards
    expected = real_hazard_per_s(20.0, [])
    assert all(h == expected for h in rec.hazards)
