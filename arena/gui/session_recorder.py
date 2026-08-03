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
