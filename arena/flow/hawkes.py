"""Exponential-kernel Hawkes process: lambda(t) = mu + sum alpha*exp(-beta(t-ti)).

The branching ratio eta = alpha/beta is the expected number of events each
event directly triggers. Note that a fitted eta is almost always < 1, because
eta >= 1 describes a process that explodes to unbounded intensity — so the
usable signal is eta's trajectory against its own peak, never a crossing of 1.
See flow/signal.py.
"""

import math
import random
from dataclasses import dataclass

from arena.flow.optimize import nelder_mead

MIN_FIT_EVENTS = 40


@dataclass
class HawkesFit:
    mu: float
    alpha: float
    beta: float
    eta: float
    loglik: float


def log_likelihood(times: list[float], mu: float, alpha: float,
                   beta: float) -> float:
    """Exact log-likelihood via the O(n) recursion for exponential kernels."""
    if not times:
        return 0.0
    if mu <= 0 or alpha <= 0 or beta <= 0:
        return -math.inf
    horizon = times[-1]
    total = 0.0
    a = 0.0  # A_i = exp(-beta*dt) * (1 + A_{i-1}); A_0 = 0
    prev = times[0]
    for i, t in enumerate(times):
        if i > 0:
            a = math.exp(-beta * (t - prev)) * (1.0 + a)
            prev = t
        lam = mu + alpha * a
        if lam <= 0:
            return -math.inf
        total += math.log(lam)
    total -= mu * horizon
    total -= (alpha / beta) * sum(1.0 - math.exp(-beta * (horizon - s))
                                  for s in times)
    return total


def fit_hawkes(times: list[float]) -> HawkesFit | None:
    """MLE of (mu, alpha, beta). Optimises in log-space so parameters stay
    positive without constrained optimisation."""
    if len(times) < MIN_FIT_EVENTS:
        return None
    base = times[0]
    rel = [t - base for t in times]
    span = rel[-1] or 1.0
    rate = len(rel) / span

    def negll(p: list[float]) -> float:
        mu, alpha, beta = math.exp(p[0]), math.exp(p[1]), math.exp(p[2])
        return -log_likelihood(rel, mu, alpha, beta)

    x0 = [math.log(max(rate * 0.5, 1e-6)), math.log(1.0), math.log(2.0)]
    best, score = nelder_mead(negll, x0, step=0.6, max_iter=600)
    mu, alpha, beta = math.exp(best[0]), math.exp(best[1]), math.exp(best[2])
    return HawkesFit(mu=mu, alpha=alpha, beta=beta, eta=alpha / beta,
                     loglik=-score)


def intensity(times: list[float], t: float, fit: HawkesFit) -> float:
    """Conditional intensity at time t given events up to t."""
    total = fit.mu
    for s in times:
        if s > t:
            break
        total += fit.alpha * math.exp(-fit.beta * (t - s))
    return total


def simulate_hawkes(mu: float, alpha: float, beta: float, horizon: float,
                    seed: int) -> list[float]:
    """Ogata's thinning algorithm. Used by tests to generate a process with
    known parameters; kept in the module so signal tests can reuse it."""
    rng = random.Random(seed)
    events: list[float] = []
    t = 0.0
    while True:
        lam_bar = mu + sum(alpha * math.exp(-beta * (t - s)) for s in events)
        if lam_bar <= 0:
            break
        t += -math.log(rng.random()) / lam_bar
        if t >= horizon:
            break
        lam_t = mu + sum(alpha * math.exp(-beta * (t - s)) for s in events)
        if rng.random() <= lam_t / lam_bar:
            events.append(t)
    return events
