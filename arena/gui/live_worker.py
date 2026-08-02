"""Threading bridge from the WebSocket to the UI, mirroring scan_worker.py:
callbacks fire FROM the worker thread and the view marshals back with
page.run_thread(). No flet import here on purpose."""

import asyncio
import threading
import time
from typing import Callable

from arena.flow.hazard import hazard_per_s
from arena.flow.signal import EXIT, SignalEngine, SignalState
from arena.gui.alerts import fire_alert
from arena.stream.subscribe import watch
from arena.stream.tape import Tape
from arena.thresholds import QME_REFIT_INTERVAL_S


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
                watch_fn=None, clock=time.monotonic) -> WatchHandle:
    handle = WatchHandle()
    watch_fn = watch_fn or watch
    tape = Tape()
    engine = SignalEngine(sensitivity)
    hazard = hazard_per_s(base_hazard_pct, [])
    last_fit = [0.0]
    alerted = [False]

    def evaluate(now: float) -> None:
        state = engine.update(now, tape.window_times(now),
                              tape.window_prices(now), hazard)
        if state.state == EXIT and not alerted[0]:
            alerted[0] = True
            fire_alert("EXIT", state.reason)
        on_state(state)

    def on_event(event) -> None:
        tape.append(event)
        now = clock()
        if now - last_fit[0] >= QME_REFIT_INTERVAL_S:
            last_fit[0] = now
            evaluate(now)

    def on_disconnect() -> None:
        on_state(engine.mark_disconnected())

    def on_reconnect() -> None:
        engine.mark_reconnected()
        alerted[0] = False
        tape.clear()

    async def run() -> None:
        await watch_fn(key, mint, on_event=on_event,
                       on_disconnect=on_disconnect, on_reconnect=on_reconnect,
                       stop=handle)

    def worker() -> None:
        asyncio.run(run())

    handle.thread = threading.Thread(target=worker, daemon=True)
    handle.thread.start()
    return handle
