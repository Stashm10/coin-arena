"""Combines two independent exit signals into one latching state machine.

Signal 1 (cascade decay): eta and lambda both falling away from their session
peaks, sustained. NOT "eta crosses 1" — see hawkes.py.
Signal 2 (stopping rule): assumed crash hazard exceeds estimated log-drift.

DISCONNECTED is a hard state: for this engine an absence of trades IS the
signal, so a dead socket is indistinguishable from a quiet coin. When
disconnected the engine reports no numbers at all rather than stale ones.
"""

from dataclasses import dataclass

from arena.flow.hawkes import MIN_FIT_EVENTS, fit_hawkes, intensity
from arena.flow.hazard import stopping_read

WARMUP = "WARMUP"
HEATING = "HEATING"
COOLING = "COOLING"
EXIT = "EXIT"
DISCONNECTED = "DISCONNECTED"


@dataclass
class Sensitivity:
    name: str
    c1: float
    c2: float
    persist_s: float


SENSITIVITIES = {
    "early": Sensitivity("early", 0.70, 0.50, 3.0),
    "balanced": Sensitivity("balanced", 0.55, 0.40, 6.0),
    "late": Sensitivity("late", 0.45, 0.30, 10.0),
}
DEFAULT_SENSITIVITY = "balanced"


@dataclass
class SignalState:
    state: str
    eta: float | None
    eta_peak: float | None
    lam: float | None
    lam_peak: float | None
    hold_drift: float | None
    reason: str


class SignalEngine:
    def __init__(self, sensitivity: str = DEFAULT_SENSITIVITY):
        self.sens = SENSITIVITIES[sensitivity]
        self._reset()

    def _reset(self) -> None:
        self.eta_peak: float | None = None
        self.lam_peak: float | None = None
        self.decay_since: float | None = None
        self.latched = False
        self.connected = True
        self.reason = ""

    def mark_disconnected(self) -> SignalState:
        self.connected = False
        return SignalState(DISCONNECTED, None, None, None, None, None,
                           "socket disconnected")

    def mark_reconnected(self) -> None:
        self._reset()

    def update(self, now: float, times: list[float],
               price_points: list[tuple[float, float]],
               hazard_ps: float) -> SignalState:
        if not self.connected:
            return self.mark_disconnected()

        # Once EXIT has latched it never un-fires, no matter how thin the
        # trade window gets afterward (e.g. trades drying up after a crash
        # — the exact scenario this signal exists to catch). Check this
        # before the MIN_FIT_EVENTS guard so a starved window degrades
        # eta/lam to None rather than reverting the state to WARMUP. We
        # still skip peak-tracking and decay/persistence bookkeeping below,
        # since none of it can change an already-latched outcome.
        if self.latched:
            read = stopping_read(price_points, hazard_ps)
            hold_drift = read.hold_drift if read else None
            fit = fit_hawkes(times)
            eta = fit.eta if fit else None
            lam = intensity(times, now, fit) if fit else None
            return self._emit(EXIT, eta, lam, hold_drift, self.reason)

        if len(times) < MIN_FIT_EVENTS:
            return SignalState(WARMUP, None, None, None, None, None,
                               f"warming up ({len(times)}/{MIN_FIT_EVENTS} trades)")

        read = stopping_read(price_points, hazard_ps)
        hold_drift = read.hold_drift if read else None

        fit = fit_hawkes(times)
        if fit is None:
            return SignalState(WARMUP, None, None, None, None, None,
                               f"warming up ({len(times)}/{MIN_FIT_EVENTS} trades)")
        lam = intensity(times, now, fit)
        self.eta_peak = fit.eta if self.eta_peak is None else max(self.eta_peak, fit.eta)
        self.lam_peak = lam if self.lam_peak is None else max(self.lam_peak, lam)

        if read is not None and read.sell:
            self.latched = True
            self.reason = "hazard exceeds drift"
            return self._emit(EXIT, fit.eta, lam, hold_drift, self.reason)

        decaying = (fit.eta < self.sens.c1 * self.eta_peak
                    and lam < self.sens.c2 * self.lam_peak)
        if decaying:
            if self.decay_since is None:
                self.decay_since = now
            elif now - self.decay_since >= self.sens.persist_s:
                self.latched = True
                self.reason = "cascade decay"
                return self._emit(EXIT, fit.eta, lam, hold_drift, self.reason)
            return self._emit(COOLING, fit.eta, lam, hold_drift,
                              "cascade cooling")
        self.decay_since = None
        return self._emit(HEATING, fit.eta, lam, hold_drift, "cascade alive")

    def _emit(self, state, eta, lam, hold_drift, reason) -> SignalState:
        return SignalState(state=state, eta=eta, eta_peak=self.eta_peak,
                           lam=lam, lam_peak=self.lam_peak,
                           hold_drift=hold_drift, reason=reason)
