"""Optimal stopping for a jump-diffusion with a Poisson total-loss jump.

For log utility with total loss on the jump, the value of continuing to hold
has log-wealth drift (mu - sigma^2/2) - lambda_c, and the optimal-stopping
boundary is simply where that turns negative. No PDE solver is needed: the
closed form is exact for this payoff.

IMPORTANT: drift here is estimated from LOG returns, and E[d ln S] =
(mu - sigma^2/2) dt. The sigma^2/2 term is therefore already inside
log_drift_per_s. Do not subtract it again.

lambda_c is an ASSUMPTION, not an estimate. It is a user-set base hazard scaled
by structural facts. Everything that displays it must label it as assumed.
"""

import math
import statistics
from dataclasses import dataclass

MIN_PRICE_POINTS = 20


@dataclass
class HazardRead:
    log_drift_per_s: float
    sigma_per_s: float
    hazard_per_s: float
    hold_drift: float
    sell: bool


def estimate_drift(points: list[tuple[float, float]]
                   ) -> tuple[float, float] | None:
    """(log_drift_per_second, sigma_per_second) from (timestamp, price) pairs.

    Pairs with a non-positive price or a non-increasing timestamp (bad,
    duplicate, or out-of-order ticks) are dropped. The drift denominator is
    the time actually covered by the retained pairs (sum of their dts), not
    the raw first-to-last window span: consecutive log-returns telescope, so
    dropping a pair removes its return from the numerator, and dividing by
    the full span instead of the retained coverage would silently bias the
    drift toward zero -- exactly the failure mode a bad tick is here to
    trigger.
    """
    if len(points) < MIN_PRICE_POINTS:
        return None
    rets, dts = [], []
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        if p0 <= 0 or p1 <= 0 or t1 <= t0:
            continue
        rets.append(math.log(p1 / p0))
        dts.append(t1 - t0)
    if len(rets) < 2:
        return None
    coverage = sum(dts)
    if coverage <= 0:
        return None
    log_drift = sum(rets) / coverage
    mean_dt = coverage / len(dts)
    var_per_step = statistics.pvariance(rets)
    sigma = math.sqrt(var_per_step / mean_dt) if mean_dt > 0 else 0.0
    return log_drift, sigma


def hazard_per_s(base_pct_per_hour: float, multipliers: list[float]) -> float:
    """Assumed crash hazard, per second. Multipliers compound."""
    rate = base_pct_per_hour / 100.0 / 3600.0
    for m in multipliers:
        rate *= m
    return rate


def stopping_read(points: list[tuple[float, float]],
                  hazard_ps: float) -> HazardRead | None:
    est = estimate_drift(points)
    if est is None:
        return None
    log_drift, sigma = est
    hold_drift = log_drift - hazard_ps
    return HazardRead(log_drift_per_s=log_drift, sigma_per_s=sigma,
                      hazard_per_s=hazard_ps, hold_drift=hold_drift,
                      sell=hold_drift < 0)
