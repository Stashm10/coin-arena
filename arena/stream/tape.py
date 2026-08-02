"""Bounded in-memory trade buffer. ~200 KB per watched mint at the default
length; nothing is persisted to SQLite."""

from collections import deque
from dataclasses import dataclass

from arena.thresholds import (QME_FIT_WINDOW_EVENTS, QME_FIT_WINDOW_SECONDS,
                              QME_TAPE_MAXLEN)


@dataclass
class TapeEvent:
    ts: float
    is_buy: bool
    sol: float
    price: float | None


class Tape:
    def __init__(self, maxlen: int = QME_TAPE_MAXLEN):
        self._events: deque[TapeEvent] = deque(maxlen=maxlen)

    def append(self, event: TapeEvent) -> None:
        self._events.append(event)

    def __len__(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()

    def _window(self, now: float) -> list[TapeEvent]:
        cutoff = now - QME_FIT_WINDOW_SECONDS
        recent = [e for e in self._events if e.ts >= cutoff]
        return recent[-QME_FIT_WINDOW_EVENTS:]

    def window_times(self, now: float) -> list[float]:
        return [e.ts for e in self._window(now)]

    def window_prices(self, now: float) -> list[tuple[float, float]]:
        return [(e.ts, e.price) for e in self._window(now) if e.price is not None]

    def buy_share(self, now: float) -> float | None:
        window = self._window(now)
        if not window:
            return None
        return sum(1 for e in window if e.is_buy) / len(window)
