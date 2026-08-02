"""Combines two independent exit signals into one latching state machine.

Signal 1 (cascade decay): eta and lambda both falling away from their session
peaks, sustained. NOT "eta crosses 1" — see hawkes.py. Needs a Hawkes fit,
which needs MIN_FIT_EVENTS trades.
Signal 2 (stopping rule): assumed crash hazard exceeds estimated log-drift.
Needs only MIN_PRICE_POINTS price points (see hazard.py) — far fewer trades
than signal 1 needs.

The two signals are genuinely independent: signal 2 is evaluated, and can
latch EXIT, before signal 1 has enough trades to even attempt a Hawkes fit.
This matters because a fast rug can collapse the price in the first ~20-39
trades — exactly the window where signal 1 is still warming up. While
warming up, a computed hold_drift is still surfaced to the caller (eta/lam
stay None, since there is genuinely no fit yet) so the UI can show it.

DISCONNECTED is a hard state: for this engine an absence of trades IS the
signal, so a dead socket is indistinguishable from a quiet coin. When
disconnected the engine reports no numbers at all rather than stale ones,
and that check has absolute precedence over both signals.
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

    def _degraded_fit(self, times: list[float], now: float):
        """Best-effort Hawkes fit for display purposes: (fit, eta, lam), with
        eta/lam None when there aren't enough events for a fit yet."""
        fit = fit_hawkes(times)
        eta = fit.eta if fit else None
        lam = intensity(times, now, fit) if fit else None
        return fit, eta, lam

    def _backfill_peaks(self, fit, lam: float | None) -> None:
        """Seed eta_peak/lam_peak from a newly available fit, or keep
        tracking the running max if they're already set.

        A fast-rug latch can fire before MIN_FIT_EVENTS trades exist, so
        eta_peak/lam_peak start out None on that EXIT. If trading continues
        while still latched and the window later crosses MIN_FIT_EVENTS,
        _degraded_fit starts returning real eta/lam — without this, the
        peaks would stay None forever while eta/lam become numbers, an
        incoherent state that crashes any renderer formatting "peak
        {eta_peak:.2f}". Treat the first available fit as this session's
        first observation and seed from it, exactly like the non-latched
        path's peak-tracking.
        """
        if fit is None:
            return
        self.eta_peak = fit.eta if self.eta_peak is None else max(self.eta_peak, fit.eta)
        self.lam_peak = lam if self.lam_peak is None else max(self.lam_peak, lam)

    def update(self, now: float, times: list[float],
               price_points: list[tuple[float, float]],
               hazard_ps: float) -> SignalState:
        if not self.connected:
            return self.mark_disconnected()

        read = stopping_read(price_points, hazard_ps)
        hold_drift = read.hold_drift if read else None

        # Once EXIT has latched it never un-fires, no matter how thin the
        # trade window gets afterward (e.g. trades drying up after a crash
        # — the exact scenario this signal exists to catch). We still skip
        # decay/persistence bookkeeping below, since none of it can change
        # an already-latched outcome. We do NOT skip peak backfilling: a
        # fast-rug latch can fire before a fit ever existed (peaks None),
        # and if trading continues past MIN_FIT_EVENTS while still latched,
        # eta/lam need a peak to report against once one becomes available.
        if self.latched:
            fit, eta, lam = self._degraded_fit(times, now)
            self._backfill_peaks(fit, lam)
            return self._emit(EXIT, eta, lam, hold_drift, self.reason)

        # Signal 2 (stopping rule) needs only MIN_PRICE_POINTS price points,
        # far fewer than signal 1's MIN_FIT_EVENTS trades — evaluate it here,
        # before any Hawkes-fit gating, so it can latch EXIT on its own even
        # while signal 1 is still warming up (e.g. a fast rug collapsing the
        # price in the first ~20-39 trades).
        if read is not None and read.sell:
            self.latched = True
            self.reason = "hazard exceeds drift"
            fit, eta, lam = self._degraded_fit(times, now)
            self._backfill_peaks(fit, lam)
            return self._emit(EXIT, eta, lam, hold_drift, self.reason)

        # fit_hawkes already self-guards on MIN_FIT_EVENTS, so a single None
        # check here covers both "too few events" and "fit failed" — no need
        # for a separate len(times) < MIN_FIT_EVENTS gate.
        fit = fit_hawkes(times)
        if fit is None:
            return SignalState(WARMUP, None, None, None, None, hold_drift,
                               f"warming up ({len(times)}/{MIN_FIT_EVENTS} trades)")
        lam = intensity(times, now, fit)
        self.eta_peak = fit.eta if self.eta_peak is None else max(self.eta_peak, fit.eta)
        self.lam_peak = lam if self.lam_peak is None else max(self.lam_peak, lam)

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
