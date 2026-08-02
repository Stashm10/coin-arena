"""Position sizing under a heavy-tailed, mostly-losing return distribution.

Standard Kelly assumes well-behaved outcomes. Memecoin returns are a mixture of
total loss and a power-law payoff, where variance can be unbounded and the
naive Kelly fraction is catastrophic. This maximises expected log growth by
Monte Carlo, then walks the fraction down until a maximum-drawdown constraint
is satisfied.

Every input is a BELIEF supplied by the user, not an estimate from data. The
sensitivity table is the real output: it shows how far the answer moves when
the belief is wrong.
"""

import math
import random
from dataclasses import dataclass

GRID = [i / 200.0 for i in range(0, 201)]  # 0.000 .. 1.000 in 0.5% steps


@dataclass
class KellyInputs:
    hit_rate: float
    winner_multiple: float
    tail_index: float
    max_drawdown: float
    ruin_tolerance: float
    trials: int = 400
    trades_per_path: int = 200
    seed: int = 12345


@dataclass
class KellyResult:
    f_star: float
    f_constrained: float
    drawdown_prob: float
    sensitivity: list[tuple[str, float]]


def _draw(rng: random.Random, hit_rate: float, x_m: float,
          alpha: float) -> float:
    """Net return multiple: -1.0 on total loss, else Pareto(x_m, alpha) - 1."""
    if rng.random() >= hit_rate:
        return -1.0
    u = rng.random()
    payoff = x_m / (u ** (1.0 / alpha))
    return payoff - 1.0


def _samples(inputs: KellyInputs, hit_rate: float) -> list[float]:
    rng = random.Random(inputs.seed)
    n = inputs.trials * inputs.trades_per_path
    return [_draw(rng, hit_rate, inputs.winner_multiple, inputs.tail_index)
            for _ in range(n)]


def _expected_log_growth(f: float, draws: list[float]) -> float:
    total = 0.0
    for x in draws:
        w = 1.0 + f * x
        if w <= 1e-12:
            return -math.inf
        total += math.log(w)
    return total / len(draws)


def _drawdown_prob(f: float, draws: list[float], inputs: KellyInputs) -> float:
    breaches = 0
    idx = 0
    for _ in range(inputs.trials):
        equity, peak = 1.0, 1.0
        breached = False
        for _ in range(inputs.trades_per_path):
            x = draws[idx]
            idx += 1
            equity *= max(1.0 + f * x, 1e-12)
            peak = max(peak, equity)
            if equity <= peak * (1.0 - inputs.max_drawdown):
                breached = True
        breaches += 1 if breached else 0
    return breaches / inputs.trials


def _solve(inputs: KellyInputs, hit_rate: float) -> tuple[float, float, float]:
    draws = _samples(inputs, hit_rate)
    best_f, best_g = 0.0, 0.0
    for f in GRID:
        g = _expected_log_growth(f, draws)
        if g > best_g:
            best_f, best_g = f, g
    constrained, prob = 0.0, 0.0
    for f in GRID:
        if f > best_f:
            break
        p = _drawdown_prob(f, draws, inputs)
        if p <= inputs.ruin_tolerance:
            constrained, prob = f, p
    return best_f, constrained, prob


def solve_kelly(inputs: KellyInputs) -> KellyResult:
    f_star, f_constrained, prob = _solve(inputs, inputs.hit_rate)
    _, half, _ = _solve(inputs, inputs.hit_rate * 0.5)
    _, double, _ = _solve(inputs, min(inputs.hit_rate * 2.0, 1.0))
    return KellyResult(
        f_star=f_star, f_constrained=f_constrained, drawdown_prob=prob,
        sensitivity=[("half hit rate", half),
                     ("stated hit rate", f_constrained),
                     ("double hit rate", double)])
