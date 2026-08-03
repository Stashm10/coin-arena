"""Threading bridge from the WebSocket to the UI, mirroring scan_worker.py:
callbacks fire FROM the worker thread and the view marshals back with
page.run_thread(). No flet import here on purpose."""

import asyncio
import logging
import threading
import time
from typing import Callable

from arena.flow.hazard import hazard_per_s
from arena.flow.signal import EXIT, SignalEngine, SignalState
from arena.gui.alerts import fire_alert
from arena.gui.session_recorder import SessionRecorder
from arena.store import Store
from arena.stream.subscribe import watch
from arena.stream.tape import Tape
from arena.thresholds import QME_REFIT_INTERVAL_S

log = logging.getLogger(__name__)


class WatchHandle:
    def __init__(self):
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None

    def stop(self) -> None:
        self._stop.set()

    def is_set(self) -> bool:
        return self._stop.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        # Delegates to the internal Event so arena.stream.subscribe.watch's
        # duck-typed `getattr(stop, "wait", None)` check finds a callable and
        # uses it to sleep out reconnect backoff interruptibly. Without this,
        # watch() silently falls back to asyncio.sleep(backoff) and a stopped
        # WatchHandle can keep the worker thread alive for up to
        # BACKOFF_MAX_S (30s) after stop() is called.
        return self._stop.wait(timeout)

    def join(self, timeout: float | None = None) -> None:
        if self.thread is not None:
            self.thread.join(timeout)


def start_watch(mint: str, key: str, sensitivity: str, base_hazard_pct: float,
                on_state: Callable[[SignalState], None],
                watch_fn=None, clock=time.monotonic,
                get_multipliers: Callable[[], list[float]] | None = None,
                recorder_factory: Callable[[], object] | None = None
                ) -> WatchHandle:
    handle = WatchHandle()
    watch_fn = watch_fn or watch
    tape = Tape()
    engine = SignalEngine(sensitivity)
    # Multipliers are re-read on every evaluation (not computed once here) so
    # that a running watch's manual toggles (mint live / concentrated /
    # creator selling) take effect immediately without restarting the watch.
    get_multipliers = get_multipliers or (lambda: [])
    last_fit = [0.0]
    alerted = [False]

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

    def on_event(event) -> None:
        tape.append(event)
        # Before the throttle, so the entry price is the first PRICED trade
        # rather than the first evaluated one.
        _safely("note_price", event.price)
        now = clock()
        if now - last_fit[0] >= QME_REFIT_INTERVAL_S:
            last_fit[0] = now
            evaluate(now)

    def on_disconnect() -> None:
        state = engine.mark_disconnected()
        on_state(state)
        _safely("note_state", state)

    def on_reconnect() -> None:
        engine.mark_reconnected()
        alerted[0] = False
        tape.clear()

    async def run() -> None:
        await watch_fn(key, mint, on_event=on_event,
                       on_disconnect=on_disconnect, on_reconnect=on_reconnect,
                       stop=handle)

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

    handle.thread = threading.Thread(target=worker, daemon=True)
    handle.thread.start()
    return handle
