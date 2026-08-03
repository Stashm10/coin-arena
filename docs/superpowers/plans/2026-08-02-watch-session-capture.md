# Watch Session Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every QME watch — its settings, its entry price, and each signal state transition — so the engine's exit signal can be measured later against real outcomes.

**Architecture:** Two new SQLite tables and a small `SessionRecorder` that sits between the watch worker and the store. The recorder writes only on state *transitions*, never per trade, so the socket path stays free of disk I/O. A recording failure can never break a live watch.

**Tech Stack:** Python 3.11+, stdlib `sqlite3` and `json`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-02-exit-measurement-harness-design.md` — **Phase 1 only.** Phases 2 (replay) and 3 (scoring/report) are explicitly out of scope; do not build them.

## Global Constraints

- **Phase 1 only.** Do not create the `watch_outcomes` table, `arena/replay.py`, or `arena/research/`. `CREATE TABLE IF NOT EXISTS` runs on every `Store()` construction, so adding that table later is free; creating it now would be an unused table.
- **A recording failure must never break a live watch.** Every store call from the recorder is wrapped and logged. The user's position matters more than the telemetry.
- **No writes on the per-trade path.** Writes happen on watch start, on the first priced trade, and on each state transition — never once per trade.
- **Transitions only.** A repeated identical `(state, reason)` must not produce a second row. The engine emits a state roughly once per second; storing all of them would be ~3,600 rows per session for no analytical gain.
- **SQLite connections are per-thread.** `Store()` must be constructed on the worker thread that uses it, never on the UI thread and passed across. `sqlite3` defaults to `check_same_thread=True` and will raise `ProgrammingError` otherwise. Follow the existing pattern in `arena/gui/scan_worker.py`, which constructs `Store()` inside the worker.
- **No numpy, scipy, pandas.** Stdlib only.
- **`arena/gui/session_recorder.py` must not import Flet.**
- **Tests run offline** — no network, no API key.
- Follow existing codebase patterns: 4-space indent, type hints on public functions, module docstrings explaining *why*, tests as plain `def test_*` functions with no test classes.
- Current baseline: **266 passed, 1 deselected.** It must not regress.

## File Structure

| File | Responsibility |
|---|---|
| `arena/store.py` | Extended with two tables and four methods (existing file) |
| `arena/gui/session_recorder.py` | Transition-dedup + failure isolation between worker and store |
| `arena/gui/live_worker.py` | Extended to construct and drive the recorder (existing file) |

---

### Task 1: Store schema and methods

**Files:**
- Modify: `arena/store.py` (append to `SCHEMA`, add four methods)
- Test: `tests/test_store_sessions.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Store.start_watch_session(mint: str, started_ts: int, sensitivity: str, hazard_pct: float, toggles: list[float]) -> int` — returns the new session id
  - `Store.set_session_entry_price(session_id: int, price: float) -> None`
  - `Store.record_watch_signal(session_id: int, ts: int, state: str, reason: str, eta: float | None, lam: float | None, hold_drift: float | None) -> None`
  - `Store.watch_session_signals(session_id: int) -> list[dict]` — ordered by `ts`, then insertion
  - `Store.recent_watch_sessions(limit: int = 50) -> list[dict]`

`toggles` is stored as a JSON array of the multiplier floats active at watch start.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_sessions.py
import json

from arena.store import Store


def _store(tmp_path):
    return Store(tmp_path / "t.db")


def test_start_session_returns_an_id_and_persists_the_row(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [2.5, 4.0])
    assert isinstance(sid, int)
    rows = store.recent_watch_sessions()
    assert len(rows) == 1
    row = rows[0]
    assert row["mint"] == "MintA"
    assert row["started_ts"] == 1000
    assert row["sensitivity"] == "balanced"
    assert row["hazard_pct"] == 20.0
    assert json.loads(row["toggles"]) == [2.5, 4.0]
    assert row["entry_price"] is None
    assert row["resolved_ts"] is None
    store.close()


def test_two_sessions_get_distinct_ids(tmp_path):
    store = _store(tmp_path)
    a = store.start_watch_session("MintA", 1000, "early", 20.0, [])
    b = store.start_watch_session("MintB", 1001, "late", 50.0, [])
    assert a != b
    assert len(store.recent_watch_sessions()) == 2
    store.close()


def test_entry_price_is_set_once_and_read_back(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.set_session_entry_price(sid, 3.5e-8)
    assert store.recent_watch_sessions()[0]["entry_price"] == 3.5e-8
    store.close()


def test_signals_persist_with_all_fields(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.record_watch_signal(sid, 1010, "HEATING", "cascade alive",
                              0.71, 4.2, 0.0003)
    rows = store.watch_session_signals(sid)
    assert len(rows) == 1
    assert rows[0]["state"] == "HEATING"
    assert rows[0]["reason"] == "cascade alive"
    assert rows[0]["eta"] == 0.71
    assert rows[0]["lam"] == 4.2
    assert rows[0]["hold_drift"] == 0.0003
    store.close()


def test_signals_accept_null_numerics(tmp_path):
    """DISCONNECTED and WARMUP carry no numbers — the columns must be
    nullable, because a stale number is worse than no number."""
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.record_watch_signal(sid, 1010, "DISCONNECTED", "socket disconnected",
                              None, None, None)
    row = store.watch_session_signals(sid)[0]
    assert row["eta"] is None and row["lam"] is None
    assert row["hold_drift"] is None
    store.close()


def test_signals_return_in_timestamp_order(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    for ts, state in [(1030, "COOLING"), (1010, "WARMUP"), (1020, "HEATING")]:
        store.record_watch_signal(sid, ts, state, "r", None, None, None)
    assert [r["state"] for r in store.watch_session_signals(sid)] == [
        "WARMUP", "HEATING", "COOLING"]
    store.close()


def test_signals_are_scoped_to_their_session(tmp_path):
    store = _store(tmp_path)
    a = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    b = store.start_watch_session("MintB", 1000, "balanced", 20.0, [])
    store.record_watch_signal(a, 1010, "HEATING", "cascade alive", None, None, None)
    assert len(store.watch_session_signals(a)) == 1
    assert store.watch_session_signals(b) == []
    store.close()


def test_recent_sessions_are_newest_first_and_respect_limit(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        store.start_watch_session(f"Mint{i}", 1000 + i, "balanced", 20.0, [])
    rows = store.recent_watch_sessions(limit=3)
    assert len(rows) == 3
    assert rows[0]["mint"] == "Mint4"
    store.close()


def test_existing_tables_still_work_after_schema_change(tmp_path):
    """The schema append must not disturb the pre-existing tables."""
    store = _store(tmp_path)
    store.set_manual_label("MintA", 1)
    assert store.manual_label("MintA") == 1
    assert store.label_counts()["labeled"] == 1
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store_sessions.py -v`
Expected: FAIL with `AttributeError: 'Store' object has no attribute 'start_watch_session'`

- [ ] **Step 3: Write minimal implementation**

Append to the `SCHEMA` string in `arena/store.py`, before its closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS watch_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    started_ts INTEGER NOT NULL,
    entry_price REAL,
    sensitivity TEXT NOT NULL,
    hazard_pct REAL NOT NULL,
    toggles TEXT NOT NULL,
    resolved_ts INTEGER
);
CREATE TABLE IF NOT EXISTS watch_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    eta REAL,
    lam REAL,
    hold_drift REAL
);
CREATE INDEX IF NOT EXISTS idx_watch_signals_session
    ON watch_signals(session_id, ts);
```

Add these methods to the `Store` class:

```python
    def start_watch_session(self, mint: str, started_ts: int, sensitivity: str,
                           hazard_pct: float, toggles: list[float]) -> int:
        cur = self.conn.execute(
            "INSERT INTO watch_sessions (mint, started_ts, sensitivity, "
            "hazard_pct, toggles) VALUES (?, ?, ?, ?, ?)",
            (mint, started_ts, sensitivity, hazard_pct, json.dumps(toggles)))
        self.conn.commit()
        return cur.lastrowid

    def set_session_entry_price(self, session_id: int, price: float) -> None:
        self.conn.execute(
            "UPDATE watch_sessions SET entry_price = ? WHERE id = ?",
            (price, session_id))
        self.conn.commit()

    def record_watch_signal(self, session_id: int, ts: int, state: str,
                            reason: str, eta: float | None, lam: float | None,
                            hold_drift: float | None) -> None:
        self.conn.execute(
            "INSERT INTO watch_signals (session_id, ts, state, reason, eta, "
            "lam, hold_drift) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, ts, state, reason, eta, lam, hold_drift))
        self.conn.commit()

    def watch_session_signals(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, state, reason, eta, lam, hold_drift FROM watch_signals "
            "WHERE session_id = ? ORDER BY ts, id", (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def recent_watch_sessions(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, mint, started_ts, entry_price, sensitivity, hazard_pct,"
            " toggles, resolved_ts FROM watch_sessions "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
```

`json` is already imported at the top of `arena/store.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_store_sessions.py tests/test_store.py tests/test_store_labels.py -v`
Expected: all pass — the pre-existing store tests must still be green after the schema change.

- [ ] **Step 5: Commit**

```bash
git add arena/store.py tests/test_store_sessions.py
git commit -m "feat: watch_sessions and watch_signals tables"
```

---

### Task 2: SessionRecorder

**Files:**
- Create: `arena/gui/session_recorder.py`
- Test: `tests/test_session_recorder.py`

**Interfaces:**
- Consumes: the `Store` methods from Task 1
- Produces:
  - `class SessionRecorder`:
    - `__init__(self, store, mint: str, sensitivity: str, hazard_pct: float, toggles: list[float], now_fn=time.time)`
    - `start(self) -> None`
    - `note_price(self, price: float | None) -> None`
    - `note_state(self, state) -> None` — `state` is a `SignalState` (duck-typed: `.state`, `.reason`, `.eta`, `.lam`, `.hold_drift`)
    - `session_id: int | None` attribute

**Two behaviours that define this class:**

1. **Transition dedup.** `note_state` writes only when `(state.state, state.reason)` differs from the last recorded pair. The engine emits roughly once per second; without this the table would grow ~3,600 rows per session for no analytical gain.
2. **Failure isolation.** Every store call is wrapped. A locked database, a disk error, or any store exception must be logged and swallowed — the user is holding a live position and a telemetry failure must never interrupt the watch or propagate into the socket loop.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_recorder.py
from dataclasses import dataclass

from arena.gui.session_recorder import SessionRecorder


@dataclass
class FakeState:
    state: str
    reason: str
    eta: float | None = None
    lam: float | None = None
    hold_drift: float | None = None


class FakeStore:
    def __init__(self, fail_on=None):
        self.sessions = []
        self.signals = []
        self.entry_prices = []
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

    def record_watch_signal(self, session_id, ts, state, reason, eta, lam,
                            hold_drift):
        if "signal" in self.fail_on:
            raise RuntimeError("db locked")
        self.signals.append((session_id, ts, state, reason, eta, lam, hold_drift))


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_session_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.gui.session_recorder'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/gui/session_recorder.py
"""Records a watch session and its state transitions for later measurement.

Two rules define this class:

Transitions only — the engine emits a state roughly once per second, so
writing every emission would produce thousands of identical rows per session
and answer no question that the transitions do not.

Failures are swallowed — the user is holding a live position. A locked
database or a disk error must never interrupt a watch or propagate into the
socket loop, so every store call is wrapped and logged. Losing telemetry is an
acceptable outcome; losing the exit signal is not.

No flet import: this runs on the watch worker thread.
"""

import logging
import time
from typing import Callable

log = logging.getLogger(__name__)


class SessionRecorder:
    def __init__(self, store, mint: str, sensitivity: str, hazard_pct: float,
                 toggles: list[float],
                 now_fn: Callable[[], float] = time.time):
        self._store = store
        self._mint = mint
        self._sensitivity = sensitivity
        self._hazard_pct = hazard_pct
        self._toggles = toggles
        self._now = now_fn
        self.session_id: int | None = None
        self._last_key: tuple[str, str] | None = None
        self._entry_done = False

    def start(self) -> None:
        try:
            self.session_id = self._store.start_watch_session(
                self._mint, int(self._now()), self._sensitivity,
                self._hazard_pct, self._toggles)
        except Exception as exc:
            log.warning("watch session not recorded: %s", exc)
            self.session_id = None

    def note_price(self, price: float | None) -> None:
        if self.session_id is None or self._entry_done or price is None:
            return
        # Marked done even on failure: a store that just raised will raise
        # again on the next trade, and retrying per-trade would put a write
        # attempt back on the hot path this class exists to keep clear.
        self._entry_done = True
        try:
            self._store.set_session_entry_price(self.session_id, price)
        except Exception as exc:
            log.warning("entry price not recorded: %s", exc)

    def note_state(self, state) -> None:
        if self.session_id is None:
            return
        key = (state.state, state.reason)
        if key == self._last_key:
            return
        self._last_key = key
        try:
            self._store.record_watch_signal(
                self.session_id, int(self._now()), state.state, state.reason,
                state.eta, state.lam, state.hold_drift)
        except Exception as exc:
            log.warning("signal not recorded: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_session_recorder.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add arena/gui/session_recorder.py tests/test_session_recorder.py
git commit -m "feat: SessionRecorder with transition dedup and failure isolation"
```

---

### Task 3: Wire the recorder into the watch worker

**Files:**
- Modify: `arena/gui/live_worker.py`
- Test: `tests/test_gui_live_worker.py` (extend)

**Interfaces:**
- Consumes: `SessionRecorder` from Task 2; `Store` from Task 1
- Produces: `start_watch(...)` gains a keyword-only parameter `recorder_factory: Callable[[], object] | None = None`. When `None`, the worker builds a `SessionRecorder` over a freshly constructed `Store()` **on the worker thread**. Tests inject a fake.

**The threading detail that will bite you.** `sqlite3` connections default to `check_same_thread=True`. `start_watch` runs on the UI thread; its `worker()` function runs on the new thread. The `Store()` must therefore be constructed **inside** `worker()`, not in `start_watch`'s body — otherwise every write raises `ProgrammingError`. `arena/gui/scan_worker.py` already follows this pattern; match it.

**Where the calls go:**
- `recorder.start()` — first thing inside `worker()`, before the event loop runs.
- `recorder.note_price(event.price)` — in `on_event`, before the refit throttle, so the entry price comes from the genuinely first priced trade rather than the first evaluated one.
- `recorder.note_state(state)` — in `evaluate`, after `on_state(state)`, so the UI updates first and a slow disk never delays the display.
- `recorder.note_state(...)` — also in `on_disconnect`, which emits a state without going through `evaluate`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gui_live_worker.py`:

```python
class FakeRecorder:
    def __init__(self):
        self.started = False
        self.prices = []
        self.states = []

    def start(self):
        self.started = True

    def note_price(self, price):
        self.prices.append(price)

    def note_state(self, state):
        self.states.append(state.state)


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

        def note_state(self, state):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_live_worker.py -v`
Expected: FAIL with `TypeError: start_watch() got an unexpected keyword argument 'recorder_factory'`

- [ ] **Step 3: Write minimal implementation**

In `arena/gui/live_worker.py`, add exactly these three imports (the file
currently has no `logging` import, and `Store`/`SessionRecorder` are new to it):

```python
import logging

from arena.gui.session_recorder import SessionRecorder
from arena.store import Store
```

and this module-level logger, after the imports:

```python
log = logging.getLogger(__name__)
```

Change the signature to add a keyword-only parameter:

```python
def start_watch(mint: str, key: str, sensitivity: str, base_hazard_pct: float,
                on_state: Callable[[SignalState], None],
                watch_fn=None, clock=time.monotonic,
                get_multipliers: Callable[[], list[float]] | None = None,
                recorder_factory: Callable[[], object] | None = None
                ) -> WatchHandle:
```

Add a null recorder and a guarded wrapper near the top of the function body, after `get_multipliers` is defaulted:

```python
    class _NullRecorder:
        """Used when a recorder cannot be built at all. Keeps the call sites
        free of None checks."""

        def start(self) -> None: ...
        def note_price(self, price) -> None: ...
        def note_state(self, state) -> None: ...

    recorder_box: list = [_NullRecorder()]

    def _safely(name: str, *args) -> None:
        """Telemetry must never break a live watch: SessionRecorder already
        swallows store errors, but a factory or an injected recorder can raise
        anywhere, so the call sites are guarded too."""
        try:
            getattr(recorder_box[0], name)(*args)
        except Exception as exc:
            log.warning("session recording failed (%s): %s", name, exc)
```

Add `import logging` and `log = logging.getLogger(__name__)` at module level if not present.

Update `evaluate` to record after the UI callback:

```python
    def evaluate(now: float) -> None:
        hazard = hazard_per_s(base_hazard_pct, get_multipliers())
        state = engine.update(now, tape.window_times(now),
                              tape.window_prices(now), hazard)
        if state.state == EXIT and not alerted[0]:
            alerted[0] = True
            fire_alert("EXIT", state.reason)
        on_state(state)
        # After on_state: the display must never wait on a disk write.
        _safely("note_state", state)
```

Update `on_event` to record the price before the refit throttle:

```python
    def on_event(event) -> None:
        tape.append(event)
        # Before the throttle, so the entry price is the first PRICED trade
        # rather than the first evaluated one.
        _safely("note_price", event.price)
        now = clock()
        if now - last_fit[0] >= QME_REFIT_INTERVAL_S:
            last_fit[0] = now
            evaluate(now)
```

Update `on_disconnect`, which emits a state without going through `evaluate`:

```python
    def on_disconnect() -> None:
        state = engine.mark_disconnected()
        on_state(state)
        _safely("note_state", state)
```

Build the recorder inside `worker()`, on the worker thread:

```python
    def _default_recorder_factory():
        # Store() MUST be constructed here, on the worker thread: sqlite3
        # defaults to check_same_thread=True and a connection made on the UI
        # thread would raise ProgrammingError on every write.
        return SessionRecorder(Store(), mint, sensitivity, base_hazard_pct,
                               get_multipliers())

    factory = recorder_factory or _default_recorder_factory

    def worker() -> None:
        try:
            recorder_box[0] = factory()
        except Exception as exc:
            log.warning("session recorder unavailable: %s", exc)
        _safely("start")
        asyncio.run(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_live_worker.py tests/test_gui_live.py -v`
Expected: all pass, including the five pre-existing live-worker tests.

Then confirm the real path works end to end against a temporary database:

```bash
.venv/bin/python -c "
import tempfile, os
os.environ['ARENA_DATA_DIR'] = tempfile.mkdtemp()
from arena.store import Store
from arena.gui.session_recorder import SessionRecorder
s = Store()
r = SessionRecorder(s, 'MintA', 'balanced', 20.0, [2.5])
r.start(); r.note_price(3e-8)
class S: state, reason, eta, lam, hold_drift = 'HEATING', 'cascade alive', 0.7, 4.0, 1e-4
r.note_state(S()); r.note_state(S())
print('session:', s.recent_watch_sessions()[0])
print('signals:', s.watch_session_signals(r.session_id))
assert len(s.watch_session_signals(r.session_id)) == 1, 'dedup failed'
print('ok')
"
```

Expected: one session row with `entry_price` set, exactly one signal row, and `ok`.

- [ ] **Step 5: Commit**

```bash
git add arena/gui/live_worker.py tests/test_gui_live_worker.py
git commit -m "feat: record watch sessions and state transitions"
```

---

## Verification checklist

Confirm each by running the command and reading the output:

- [ ] `.venv/bin/pytest` — full suite green (baseline was 266 passed, 1 deselected)
- [ ] `.venv/bin/python -c "import arena.gui.session_recorder"` — imports without Flet
- [ ] `grep -n "watch_outcomes" arena/` — no matches (Phase 2 is out of scope)
- [ ] `ls arena/replay.py arena/research 2>&1` — both absent (Phases 2 and 3 out of scope)
- [ ] Run a real watch on a live mint, stop it, then confirm rows landed:
      `.venv/bin/python -c "from arena.store import Store; s=Store(); print(s.recent_watch_sessions(5))"`
- [ ] Confirm the signals table holds transitions, not one row per second, for that session
