from dataclasses import dataclass

from arena.gui.session_recorder import SessionRecorder


@dataclass
class FakeState:
    state: str
    reason: str
    eta: float | None = None
    eta_peak: float | None = None
    lam: float | None = None
    lam_peak: float | None = None
    hold_drift: float | None = None


class FakeStore:
    def __init__(self, fail_on=None):
        self.sessions = []
        self.signals = []
        self.entry_prices = []
        self.ended = []
        self.fail_on = fail_on or set()

    def start_watch_session(self, mint, started_ts, sensitivity, hazard_pct,
                            toggles):
        if "start" in self.fail_on:
            raise RuntimeError("db locked")
        self.sessions.append((mint, started_ts, sensitivity, hazard_pct, toggles))
        return len(self.sessions)

    def set_session_entry_price(self, session_id, price):
        if "price" in self.fail_on:
            raise RuntimeError("db locked")
        self.entry_prices.append((session_id, price))

    def end_watch_session(self, session_id, ended_ts):
        if "finish" in self.fail_on:
            raise RuntimeError("db locked")
        self.ended.append((session_id, ended_ts))

    def record_watch_signal(self, session_id, ts, state, reason, eta, lam,
                            hold_drift, hazard_per_s=None, eta_peak=None,
                            lam_peak=None):
        if "signal" in self.fail_on:
            raise RuntimeError("db locked")
        self.signals.append((session_id, ts, state, reason, eta, lam,
                             hold_drift, hazard_per_s, eta_peak, lam_peak))


def _recorder(store, **kw):
    opts = dict(mint="MintA", sensitivity="balanced", hazard_pct=20.0,
                toggles=[], now_fn=lambda: 1000)
    opts.update(kw)
    return SessionRecorder(store, **opts)


def test_start_creates_a_session_and_records_its_id():
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    assert rec.session_id == 1
    assert store.sessions[0][0] == "MintA"
    assert store.sessions[0][1] == 1000


def test_first_price_sets_entry_and_later_prices_do_not():
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_price(3.0)
    rec.note_price(9.0)
    assert store.entry_prices == [(1, 3.0)]


def test_none_prices_are_ignored_until_a_real_one_arrives():
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_price(None)
    rec.note_price(None)
    rec.note_price(5.0)
    assert store.entry_prices == [(1, 5.0)]


def test_state_transitions_are_recorded():
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("WARMUP", "warming up (5/40 trades)"))
    rec.note_state(FakeState("HEATING", "cascade alive", 0.7, 4.0, 0.001))
    assert [s[2] for s in store.signals] == ["WARMUP", "HEATING"]
    assert store.signals[1][4] == 0.7


def test_repeated_identical_states_are_not_recorded_twice():
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    for _ in range(50):
        rec.note_state(FakeState("HEATING", "cascade alive", 0.7, 4.0, 0.001))
    assert len(store.signals) == 1


def test_same_state_with_a_new_reason_is_a_transition():
    """WARMUP's reason carries a trade counter, and EXIT's reason names which
    signal fired — a reason change is a real event, not noise."""
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("EXIT", "cascade decay"))
    rec.note_state(FakeState("EXIT", "hazard exceeds drift"))
    assert len(store.signals) == 2


def test_returning_to_a_prior_state_records_again():
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("HEATING", "cascade alive"))
    rec.note_state(FakeState("COOLING", "cascade cooling"))
    rec.note_state(FakeState("HEATING", "cascade alive"))
    assert [s[2] for s in store.signals] == ["HEATING", "COOLING", "HEATING"]


def test_a_failing_start_does_not_raise_and_disables_recording():
    store = FakeStore(fail_on={"start"})
    rec = _recorder(store)
    rec.start()                      # must not raise
    assert rec.session_id is None
    rec.note_state(FakeState("HEATING", "cascade alive"))  # must not raise
    rec.note_price(1.0)              # must not raise
    assert store.signals == []


def test_a_failing_signal_write_does_not_raise():
    store = FakeStore(fail_on={"signal"})
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("HEATING", "cascade alive"))  # must not raise


def test_a_failing_price_write_does_not_raise_and_does_not_retry_forever():
    store = FakeStore(fail_on={"price"})
    rec = _recorder(store)
    rec.start()
    rec.note_price(1.0)   # must not raise
    rec.note_price(2.0)
    assert store.entry_prices == []


def test_notes_before_start_are_ignored():
    store = FakeStore()
    rec = _recorder(store)
    rec.note_state(FakeState("HEATING", "cascade alive"))
    rec.note_price(1.0)
    assert store.signals == []
    assert store.entry_prices == []


def test_finish_records_the_end_of_the_session():
    """Finding 1: nothing recorded when a watch stopped means duration is
    unknowable. finish() must write ended_ts."""
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.finish()
    assert store.ended == [(1, 1000)]


def test_finish_before_start_is_ignored():
    store = FakeStore()
    rec = _recorder(store)
    rec.finish()  # must not raise
    assert store.ended == []


def test_a_failing_finish_does_not_raise():
    store = FakeStore(fail_on={"finish"})
    rec = _recorder(store)
    rec.start()
    rec.finish()  # must not raise
    assert store.ended == []


def test_note_state_records_the_effective_hazard_used():
    """Finding 2: get_multipliers() is re-read on every evaluation, so only
    the per-signal hazard (not the session-level toggle snapshot) says what
    actually produced a given transition."""
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("HEATING", "cascade alive"), hazard_ps=0.0031)
    assert store.signals[0][7] == 0.0031


def test_note_state_defaults_hazard_to_none():
    """Default keeps existing call sites (and this file's other tests)
    valid without passing a hazard."""
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("HEATING", "cascade alive"))
    assert store.signals[0][7] is None


def test_hazard_change_alone_is_not_a_new_transition():
    """The dedup key stays (state, reason) — a hazard_ps change must not by
    itself create a new row."""
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("HEATING", "cascade alive"), hazard_ps=0.001)
    rec.note_state(FakeState("HEATING", "cascade alive"), hazard_ps=0.002)
    assert len(store.signals) == 1


def test_note_state_records_eta_peak_and_lam_peak():
    """Finding 3: the cascade-decay signal fires by comparing eta/lam
    against their peaks, so persisting only eta/lam loses the
    fraction-of-peak that triggered it."""
    store = FakeStore()
    rec = _recorder(store)
    rec.start()
    rec.note_state(FakeState("EXIT", "cascade decay", eta=0.3, eta_peak=0.9,
                             lam=1.0, lam_peak=5.0))
    assert store.signals[0][8] == 0.9
    assert store.signals[0][9] == 5.0
