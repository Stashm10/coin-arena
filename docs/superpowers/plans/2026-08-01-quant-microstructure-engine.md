# Quant Microstructure Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second mode to Coin Arena — a live exit engine that fits a Hawkes process to a coin's trade stream and applies a closed-form optimal-stopping rule — plus an opt-in funding-entropy trace for the existing rug checker.

**Architecture:** Two new packages with a hard boundary: `arena/flow/` is pure math over lists of numbers (no network, no I/O, no Flet), `arena/stream/` moves bytes over a Helius WebSocket and does no arithmetic. The GUI gains a two-door mode picker. The existing rug checker, its history, its labeling, and its logistic model are untouched except for one new opt-in button.

**Tech Stack:** Python 3.11+, `httpx` (existing), `websockets` (new), `flet>=0.86` (existing, GUI extra), `pytest`/`pytest-asyncio` (existing, dev extra). All math is stdlib only.

**Spec:** `docs/superpowers/specs/2026-08-01-quant-microstructure-engine-design.md`

## Global Constraints

- **Free tier only.** No paid APIs, no metered endpoints, no funded wallets. PumpPortal `subscribeTokenTrade` is forbidden (metered at 0.01 SOL/10k events).
- **Advisory only.** The app never holds a private key, never signs, never submits a transaction.
- **Never runs when closed.** No daemon, no background process, no launch agent. Sockets open on Watch, close on stop or window close.
- **No numpy, no scipy, no pandas.** All math in `arena/flow/` is Python stdlib (`math`, `random`, `statistics`). The packaged `.app` must not grow.
- **`scikit-learn` stays in the optional `ml` extra.** Never imported at runtime by the app.
- **Never display millisecond precision.** Timestamps are local arrival times with 50–200 ms network jitter. UI shows seconds.
- **`λ_c` is labeled an assumption everywhere it appears in the UI.** Never presented as an estimate.
- **Engine never writes to SQLite.** Only `funding_edges` (Task 10) is persisted, and only from the rug-checker side.
- **Existing behavior is preserved.** The six checks, verdicts, History, manual labeling, and the logistic model line all keep working exactly as they do today.
- **Tests run offline.** `pytest` must pass with no network and no API key. Live tests go behind the existing `@pytest.mark.live` marker.
- **Engine code never imports Flet.** `arena/flow/` and `arena/stream/` must be importable without the `gui` extra installed.

## File Structure

| File | Responsibility |
|---|---|
| `arena/flow/__init__.py` | Empty package marker |
| `arena/flow/optimize.py` | Nelder–Mead simplex minimizer (pure) |
| `arena/flow/hawkes.py` | Exponential-kernel Hawkes log-likelihood, fit, intensity |
| `arena/flow/hazard.py` | Log-drift/volatility estimation, hazard assembly, stopping rule |
| `arena/flow/signal.py` | State machine combining cascade decay + stopping rule |
| `arena/flow/kelly.py` | Ruin-constrained Monte-Carlo position sizing |
| `arena/flow/tips.py` | Jito landed-tip percentile fetch and recommendation |
| `arena/stream/__init__.py` | Empty package marker |
| `arena/stream/decode.py` | pump.fun `TradeEvent` Borsh decode from log payloads |
| `arena/stream/tape.py` | Bounded per-mint ring buffer |
| `arena/stream/subscribe.py` | Helius `logsSubscribe` client, heartbeat, reconnect |
| `arena/checks/entropy.py` | `H(F)` over a buyer→root mapping (pure) |
| `arena/funding_graph.py` | k-hop backward funding walk, root detection, edge cache |
| `arena/gui/alerts.py` | macOS sound + notification via `subprocess` |
| `arena/gui/live_worker.py` | Threading bridge from the socket to the UI |
| `arena/gui/trace_worker.py` | Off-thread runner for the funding-graph walk |
| `arena/gui/sizing_worker.py` | Off-thread runners for Kelly and tip lookup |
| `arena/gui/views/mode_picker.py` | Two-door launch screen |
| `arena/gui/views/live.py` | QME screen |
| `arena/gui/views/sizing.py` | Sizing and tip panel, reached from the QME |
| `arena/thresholds.py` | Extended with QME tunables (existing file) |
| `arena/store.py` | Extended with `funding_edges` table (existing file) |

**Task order rationale:** Tasks 1–5 are pure math with zero dependencies on anything else, so they can be verified in complete isolation. Tasks 6–8 build the stream. Tasks 9–10 do entropy. Tasks 11–14 wire the GUI. Nothing depends on a later task.

---

### Task 1: Nelder–Mead minimizer

**Files:**
- Create: `arena/flow/__init__.py` (empty)
- Create: `arena/flow/optimize.py`
- Test: `tests/test_flow_optimize.py`

**Interfaces:**
- Consumes: nothing
- Produces: `nelder_mead(f: Callable[[list[float]], float], x0: list[float], step: float = 0.5, max_iter: int = 300, tol: float = 1e-7) -> tuple[list[float], float]` returning `(best_point, best_score)`. Minimizes `f`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_optimize.py
import math

from arena.flow.optimize import nelder_mead


def test_finds_minimum_of_quadratic_bowl():
    def f(p):
        return (p[0] - 3.0) ** 2 + (p[1] + 1.5) ** 2

    point, score = nelder_mead(f, [0.0, 0.0])
    assert abs(point[0] - 3.0) < 1e-3
    assert abs(point[1] + 1.5) < 1e-3
    assert score < 1e-6


def test_finds_minimum_of_rosenbrock():
    def f(p):
        return (1 - p[0]) ** 2 + 100 * (p[1] - p[0] ** 2) ** 2

    point, _ = nelder_mead(f, [-1.0, 1.0], max_iter=2000)
    assert abs(point[0] - 1.0) < 1e-2
    assert abs(point[1] - 1.0) < 1e-2


def test_handles_non_finite_scores_without_crashing():
    def f(p):
        if p[0] < 0:
            return math.inf
        return (p[0] - 2.0) ** 2

    point, score = nelder_mead(f, [1.0])
    assert abs(point[0] - 2.0) < 1e-3
    assert math.isfinite(score)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_optimize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.flow'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/flow/__init__.py
```

```python
# arena/flow/optimize.py
"""Nelder-Mead simplex minimizer. Pure stdlib: the app is packaged with
`flet pack` and must not carry scipy."""

import math
from typing import Callable


def nelder_mead(f: Callable[[list[float]], float], x0: list[float],
                step: float = 0.5, max_iter: int = 300,
                tol: float = 1e-7) -> tuple[list[float], float]:
    n = len(x0)

    def safe(p: list[float]) -> float:
        try:
            v = f(p)
        except (ValueError, OverflowError, ZeroDivisionError):
            return math.inf
        return v if math.isfinite(v) else math.inf

    simplex = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step
        simplex.append(p)
    scores = [safe(p) for p in simplex]

    for _ in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: scores[i])
        simplex = [simplex[i] for i in order]
        scores = [scores[i] for i in order]
        if math.isfinite(scores[-1]) and abs(scores[-1] - scores[0]) < tol:
            break
        centroid = [sum(p[i] for p in simplex[:-1]) / n for i in range(n)]
        worst = simplex[-1]
        refl = [centroid[i] + (centroid[i] - worst[i]) for i in range(n)]
        f_refl = safe(refl)
        if f_refl < scores[0]:
            expanded = [centroid[i] + 2.0 * (centroid[i] - worst[i]) for i in range(n)]
            f_exp = safe(expanded)
            simplex[-1], scores[-1] = ((expanded, f_exp) if f_exp < f_refl
                                       else (refl, f_refl))
        elif f_refl < scores[-2]:
            simplex[-1], scores[-1] = refl, f_refl
        else:
            contracted = [centroid[i] + 0.5 * (worst[i] - centroid[i]) for i in range(n)]
            f_con = safe(contracted)
            if f_con < scores[-1]:
                simplex[-1], scores[-1] = contracted, f_con
            else:
                for i in range(1, n + 1):
                    simplex[i] = [simplex[0][j] + 0.5 * (simplex[i][j] - simplex[0][j])
                                  for j in range(n)]
                    scores[i] = safe(simplex[i])

    best = min(range(n + 1), key=lambda i: scores[i])
    return simplex[best], scores[best]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_optimize.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add arena/flow/__init__.py arena/flow/optimize.py tests/test_flow_optimize.py
git commit -m "feat: pure-Python Nelder-Mead minimizer for flow module"
```

---

### Task 2: Hawkes process fit

**Files:**
- Create: `arena/flow/hawkes.py`
- Test: `tests/test_flow_hawkes.py`

**Interfaces:**
- Consumes: `nelder_mead` from `arena.flow.optimize`
- Produces:
  - `MIN_FIT_EVENTS: int = 40`
  - `@dataclass HawkesFit: mu: float; alpha: float; beta: float; eta: float; loglik: float`
  - `fit_hawkes(times: list[float]) -> HawkesFit | None` — `times` are seconds, ascending, relative or absolute (the function re-bases internally). Returns `None` if `len(times) < MIN_FIT_EVENTS`.
  - `intensity(times: list[float], t: float, fit: HawkesFit) -> float`
  - `log_likelihood(times: list[float], mu: float, alpha: float, beta: float) -> float`
  - `simulate_hawkes(mu: float, alpha: float, beta: float, horizon: float, seed: int) -> list[float]` — Ogata thinning, lives in the module (not tests) so the state-machine tests in Task 3 can reuse it.

**Background for the implementer:** A Hawkes process is a point process where each event temporarily raises the chance of the next one — a buy triggering more buys. With an exponential kernel the intensity is `λ(t) = μ + Σ α·exp(−β(t − tᵢ))`. The branching ratio `η = α/β` is the expected number of events each event directly triggers. The likelihood below uses the standard O(n) recursion; do not write the naive O(n²) double loop.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_hawkes.py
import math

from arena.flow.hawkes import (MIN_FIT_EVENTS, fit_hawkes, intensity,
                               log_likelihood, simulate_hawkes)


def test_returns_none_below_minimum_events():
    assert fit_hawkes([float(i) for i in range(MIN_FIT_EVENTS - 1)]) is None


def test_recovers_known_branching_ratio_from_simulated_process():
    # eta = alpha/beta = 1.2/2.0 = 0.6
    times = simulate_hawkes(mu=0.5, alpha=1.2, beta=2.0, horizon=600.0, seed=7)
    assert len(times) > 200, "simulator produced too few events to fit"
    fit = fit_hawkes(times)
    assert fit is not None
    # MLE on a finite sample is noisy; assert the estimate lands in the right
    # neighbourhood, not on the nose.
    assert 0.35 < fit.eta < 0.85
    assert 0.2 < fit.mu < 1.2


def test_recovers_low_branching_ratio_as_lower_than_high_one():
    quiet = simulate_hawkes(mu=0.5, alpha=0.2, beta=2.0, horizon=600.0, seed=11)
    hot = simulate_hawkes(mu=0.5, alpha=1.6, beta=2.0, horizon=600.0, seed=11)
    quiet_fit, hot_fit = fit_hawkes(quiet), fit_hawkes(hot)
    assert quiet_fit is not None and hot_fit is not None
    assert quiet_fit.eta < hot_fit.eta


def test_log_likelihood_matches_naive_formula_on_small_input():
    times = [0.0, 1.0, 1.5, 4.0]
    mu, alpha, beta = 0.3, 0.8, 1.5
    horizon = times[-1]
    naive = 0.0
    for i, t in enumerate(times):
        lam = mu + sum(alpha * math.exp(-beta * (t - s)) for s in times[:i])
        naive += math.log(lam)
    naive -= mu * horizon
    naive -= (alpha / beta) * sum(1 - math.exp(-beta * (horizon - s)) for s in times)
    assert abs(log_likelihood(times, mu, alpha, beta) - naive) < 1e-9


def test_intensity_decays_after_last_event():
    times = [0.0, 1.0, 2.0]
    fit = type("F", (), {"mu": 0.1, "alpha": 1.0, "beta": 1.0})()
    near = intensity(times, 2.0, fit)
    far = intensity(times, 20.0, fit)
    assert near > far
    assert abs(far - 0.1) < 1e-6  # decays back to baseline mu


def test_simulator_is_deterministic_for_a_seed():
    a = simulate_hawkes(0.5, 1.0, 2.0, 100.0, seed=3)
    b = simulate_hawkes(0.5, 1.0, 2.0, 100.0, seed=3)
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_hawkes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.flow.hawkes'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/flow/hawkes.py
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


def intensity(times: list[float], t: float, fit) -> float:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_hawkes.py -v`
Expected: 6 passed. If `test_recovers_known_branching_ratio_from_simulated_process` fails, do NOT widen the assertion bounds — first check the recursion against `test_log_likelihood_matches_naive_formula_on_small_input`, which isolates the likelihood from the optimiser.

- [ ] **Step 5: Commit**

```bash
git add arena/flow/hawkes.py tests/test_flow_hawkes.py
git commit -m "feat: exponential-kernel Hawkes fit with O(n) likelihood"
```

---

### Task 3: Hazard and the stopping rule

**Files:**
- Create: `arena/flow/hazard.py`
- Modify: `arena/thresholds.py` (append QME hazard constants)
- Test: `tests/test_flow_hazard.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `@dataclass HazardRead: log_drift_per_s: float; sigma_per_s: float; hazard_per_s: float; hold_drift: float; sell: bool`
  - `estimate_drift(points: list[tuple[float, float]]) -> tuple[float, float] | None` — `points` are `(timestamp_s, price)`; returns `(log_drift_per_s, sigma_per_s)`, or `None` with fewer than `MIN_PRICE_POINTS` points or a zero time span.
  - `hazard_per_s(base_pct_per_hour: float, multipliers: list[float]) -> float`
  - `stopping_read(points, hazard_ps: float) -> HazardRead | None`
  - `MIN_PRICE_POINTS: int = 20`

**Critical correctness note for the implementer:** the drift is estimated from *log* returns, and `E[d ln S] = (μ − σ²/2)dt`. So `sum(log returns)/T` already **is** `μ − σ²/2`. Do **not** subtract `σ²/2` a second time. The hold rule is therefore `log_drift_per_s − hazard_per_s < 0 → sell`. `σ` is computed for display only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_hazard.py
import math

from arena.flow.hazard import (MIN_PRICE_POINTS, estimate_drift, hazard_per_s,
                               stopping_read)


def _ramp(rate_per_s: float, n: int = 60, dt: float = 1.0):
    """Deterministic exponential price path with known log-drift."""
    return [(i * dt, math.exp(rate_per_s * i * dt)) for i in range(n)]


def test_returns_none_below_minimum_points():
    assert estimate_drift(_ramp(0.01, n=MIN_PRICE_POINTS - 1)) is None


def test_recovers_known_log_drift_from_clean_ramp():
    drift, sigma = estimate_drift(_ramp(0.01))
    assert abs(drift - 0.01) < 1e-9
    assert sigma >= 0.0


def test_negative_ramp_gives_negative_drift():
    drift, _ = estimate_drift(_ramp(-0.02))
    assert drift < 0


def test_hazard_converts_percent_per_hour_to_per_second():
    # 36%/hr with no multipliers
    assert abs(hazard_per_s(36.0, []) - 0.36 / 3600.0) < 1e-12


def test_hazard_multipliers_compound():
    base = hazard_per_s(10.0, [])
    scaled = hazard_per_s(10.0, [2.0, 1.5])
    assert abs(scaled - base * 3.0) < 1e-12


def test_sells_when_hazard_exceeds_drift():
    read = stopping_read(_ramp(0.001), hazard_ps=0.01)
    assert read.sell is True
    assert read.hold_drift < 0


def test_holds_when_drift_exceeds_hazard():
    read = stopping_read(_ramp(0.05), hazard_ps=0.01)
    assert read.sell is False
    assert read.hold_drift > 0


def test_stopping_read_none_without_enough_points():
    assert stopping_read(_ramp(0.01, n=5), hazard_ps=0.01) is None


def test_sigma_is_zero_on_a_perfectly_smooth_path():
    _, sigma = estimate_drift(_ramp(0.01))
    assert sigma < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_hazard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.flow.hazard'`

- [ ] **Step 3: Write minimal implementation**

Append to `arena/thresholds.py`:

```python
# --- Quant Microstructure Engine ---
QME_BASE_HAZARD_PCT_PER_HOUR = 20.0   # assumed, user-adjustable — NOT estimated
QME_HAZARD_MULT_MINT_LIVE = 2.5       # mint authority still held by the dev
QME_HAZARD_MULT_CONCENTRATED = 1.8    # top-10 concentration above the warning cut
QME_HAZARD_MULT_CREATOR_SELLING = 4.0 # creator wallet observed selling
QME_FIT_WINDOW_EVENTS = 300
QME_FIT_WINDOW_SECONDS = 120.0
QME_REFIT_INTERVAL_S = 1.0
QME_TAPE_MAXLEN = 2000
```

Create `arena/flow/hazard.py`:

```python
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
    """(log_drift_per_second, sigma_per_second) from (timestamp, price) pairs."""
    if len(points) < MIN_PRICE_POINTS:
        return None
    span = points[-1][0] - points[0][0]
    if span <= 0:
        return None
    rets, dts = [], []
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        if p0 <= 0 or p1 <= 0 or t1 <= t0:
            continue
        rets.append(math.log(p1 / p0))
        dts.append(t1 - t0)
    if len(rets) < 2:
        return None
    log_drift = sum(rets) / span
    mean_dt = sum(dts) / len(dts)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_hazard.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add arena/flow/hazard.py arena/thresholds.py tests/test_flow_hazard.py
git commit -m "feat: closed-form optimal-stopping rule with assumed crash hazard"
```

---

### Task 4: Signal state machine

**Files:**
- Create: `arena/flow/signal.py`
- Test: `tests/test_flow_signal.py`

**Interfaces:**
- Consumes: `fit_hawkes`, `intensity`, `HawkesFit`, `MIN_FIT_EVENTS` from `arena.flow.hawkes`; `stopping_read`, `HazardRead` from `arena.flow.hazard`; window constants from `arena.thresholds`
- Produces:
  - Constants `WARMUP`, `HEATING`, `COOLING`, `EXIT`, `DISCONNECTED` (strings)
  - `@dataclass Sensitivity: name: str; c1: float; c2: float; persist_s: float`
  - `SENSITIVITIES: dict[str, Sensitivity]` with keys `"early"`, `"balanced"`, `"late"`; `DEFAULT_SENSITIVITY = "balanced"`
  - `@dataclass SignalState: state: str; eta: float | None; eta_peak: float | None; lam: float | None; lam_peak: float | None; hold_drift: float | None; reason: str`
  - `class SignalEngine`:
    - `__init__(self, sensitivity: str = DEFAULT_SENSITIVITY)`
    - `update(self, now: float, times: list[float], price_points: list[tuple[float, float]], hazard_ps: float) -> SignalState`
    - `mark_disconnected(self) -> SignalState`
    - `mark_reconnected(self) -> None`

**Behavioral requirements:**
- Below `MIN_FIT_EVENTS` events → `WARMUP`.
- `DISCONNECTED` suppresses all numbers: `eta`, `lam`, `hold_drift` are `None`. Stale values must never be shown. Reconnection returns to `WARMUP`, and `update` must refuse to leave `WARMUP` until the window has refilled to `MIN_FIT_EVENTS`.
- `EXIT` latches: once fired it stays until the engine is reset by disconnect/reconnect.
- Decay condition: `eta < c1*eta_peak AND lam < c2*lam_peak`, continuously true for `persist_s`. A momentary dip that recovers must NOT fire.
- Stopping condition fires immediately when `stopping_read(...).sell` is true (no persistence requirement — a crash signal shouldn't wait).
- `reason` says which condition fired: `"cascade decay"` or `"hazard exceeds drift"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_signal.py
from arena.flow.hawkes import MIN_FIT_EVENTS, simulate_hawkes
from arena.flow.signal import (COOLING, DISCONNECTED, EXIT, HEATING,
                               SENSITIVITIES, WARMUP, SignalEngine)


def _steady_points(n=60, price=1.0):
    return [(float(i), price) for i in range(n)]


def _rising_points(n=60):
    return [(float(i), 1.0 + 0.05 * i) for i in range(n)]


def test_warmup_below_minimum_events():
    eng = SignalEngine()
    state = eng.update(now=10.0, times=[float(i) for i in range(5)],
                       price_points=_rising_points(), hazard_ps=0.0)
    assert state.state == WARMUP
    assert state.eta is None


def test_disconnected_suppresses_all_numbers():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    eng.update(now=times[-1], times=times, price_points=_rising_points(),
               hazard_ps=0.0)
    state = eng.mark_disconnected()
    assert state.state == DISCONNECTED
    assert state.eta is None and state.lam is None and state.hold_drift is None


def test_reconnect_returns_to_warmup_until_window_refills():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    eng.update(now=times[-1], times=times, price_points=_rising_points(),
               hazard_ps=0.0)
    eng.mark_disconnected()
    eng.mark_reconnected()
    state = eng.update(now=0.0, times=[0.0, 1.0], price_points=_rising_points(),
                       hazard_ps=0.0)
    assert state.state == WARMUP


def test_hazard_above_drift_fires_exit_immediately():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    assert len(times) >= MIN_FIT_EVENTS
    state = eng.update(now=times[-1], times=times,
                       price_points=_steady_points(),  # zero drift
                       hazard_ps=0.01)                 # any hazard beats it
    assert state.state == EXIT
    assert state.reason == "hazard exceeds drift"


def test_healthy_rising_coin_does_not_fire():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.8, 2.0, 200.0, seed=5)
    state = eng.update(now=times[-1], times=times,
                       price_points=_rising_points(), hazard_ps=1e-9)
    assert state.state in (HEATING, COOLING)
    assert state.state != EXIT


def test_momentary_dip_does_not_fire_before_persistence_elapses():
    eng = SignalEngine(sensitivity="late")  # persist_s = 10
    hot = simulate_hawkes(1.0, 1.9, 2.0, 200.0, seed=5)
    eng.update(now=hot[-1], times=hot, price_points=_rising_points(),
               hazard_ps=1e-9)
    quiet = hot[:MIN_FIT_EVENTS + 5]
    dipped = eng.update(now=hot[-1] + 1.0, times=quiet,
                        price_points=_rising_points(), hazard_ps=1e-9)
    assert dipped.state != EXIT  # 1s < 10s persistence
    recovered = eng.update(now=hot[-1] + 2.0, times=hot,
                           price_points=_rising_points(), hazard_ps=1e-9)
    assert recovered.state != EXIT


def test_exit_latches_once_fired():
    eng = SignalEngine()
    times = simulate_hawkes(1.0, 1.5, 2.0, 200.0, seed=5)
    eng.update(now=times[-1], times=times, price_points=_steady_points(),
               hazard_ps=0.01)
    later = eng.update(now=times[-1] + 5.0, times=times,
                       price_points=_rising_points(), hazard_ps=1e-12)
    assert later.state == EXIT


def test_sensitivity_presets_are_ordered():
    early, balanced, late = (SENSITIVITIES["early"], SENSITIVITIES["balanced"],
                             SENSITIVITIES["late"])
    assert early.c1 > balanced.c1 > late.c1
    assert early.persist_s < balanced.persist_s < late.persist_s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_signal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.flow.signal'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/flow/signal.py
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
        if len(times) < MIN_FIT_EVENTS:
            return SignalState(WARMUP, None, None, None, None, None,
                               f"warming up ({len(times)}/{MIN_FIT_EVENTS} trades)")
        fit = fit_hawkes(times)
        if fit is None:
            return SignalState(WARMUP, None, None, None, None, None,
                               "warming up")
        lam = intensity(times, now, fit)
        self.eta_peak = fit.eta if self.eta_peak is None else max(self.eta_peak, fit.eta)
        self.lam_peak = lam if self.lam_peak is None else max(self.lam_peak, lam)

        read = stopping_read(price_points, hazard_ps)
        hold_drift = read.hold_drift if read else None

        if self.latched:
            return self._emit(EXIT, fit.eta, lam, hold_drift, self.reason)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_signal.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add arena/flow/signal.py tests/test_flow_signal.py
git commit -m "feat: latching exit-signal state machine with hard disconnected state"
```

---

### Task 5: Ruin-constrained Kelly sizing

**Files:**
- Create: `arena/flow/kelly.py`
- Test: `tests/test_flow_kelly.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `@dataclass KellyInputs: hit_rate: float; winner_multiple: float; tail_index: float; max_drawdown: float; ruin_tolerance: float; trials: int = 400; trades_per_path: int = 200; seed: int = 12345`
  - `@dataclass KellyResult: f_star: float; f_constrained: float; drawdown_prob: float; sensitivity: list[tuple[str, float]]`
  - `solve_kelly(inputs: KellyInputs) -> KellyResult`

**Semantics:** each trade returns `-1.0` (total loss) with probability `1 − hit_rate`, else a Pareto draw with scale `winner_multiple` and index `tail_index`, expressed as a net multiple (a draw of 3.0 means +200%). `f_star` maximizes `E[ln(1 + f·X)]` on a grid; `f_constrained` is the largest grid `f ≤ f_star` whose simulated `P(drawdown > max_drawdown) ≤ ruin_tolerance`. `sensitivity` reports `f_constrained` recomputed at half and double the stated hit rate — the point of the module.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_kelly.py
from arena.flow.kelly import KellyInputs, solve_kelly


def _inputs(**kw):
    base = dict(hit_rate=0.10, winner_multiple=5.0, tail_index=1.8,
                max_drawdown=0.50, ruin_tolerance=0.05, trials=300,
                trades_per_path=150, seed=99)
    base.update(kw)
    return KellyInputs(**base)


def test_is_deterministic_for_a_seed():
    a, b = solve_kelly(_inputs()), solve_kelly(_inputs())
    assert a.f_star == b.f_star
    assert a.f_constrained == b.f_constrained


def test_fractions_are_within_unit_interval():
    r = solve_kelly(_inputs())
    assert 0.0 <= r.f_constrained <= r.f_star <= 1.0


def test_higher_hit_rate_allows_larger_bets():
    low = solve_kelly(_inputs(hit_rate=0.05))
    high = solve_kelly(_inputs(hit_rate=0.25))
    assert high.f_star >= low.f_star


def test_hopeless_edge_sizes_to_zero():
    r = solve_kelly(_inputs(hit_rate=0.01, winner_multiple=1.2))
    assert r.f_star == 0.0


def test_drawdown_constraint_binds():
    loose = solve_kelly(_inputs(max_drawdown=0.95, ruin_tolerance=0.50))
    tight = solve_kelly(_inputs(max_drawdown=0.10, ruin_tolerance=0.01))
    assert tight.f_constrained <= loose.f_constrained


def test_sensitivity_reports_half_and_double_hit_rate():
    r = solve_kelly(_inputs())
    labels = [row[0] for row in r.sensitivity]
    assert labels == ["half hit rate", "stated hit rate", "double hit rate"]
    assert r.sensitivity[1][1] == r.f_constrained
    assert r.sensitivity[0][1] <= r.sensitivity[2][1]


def test_fatter_tail_is_not_penalised_versus_thinner():
    # smaller tail_index = fatter tail = bigger winners
    fat = solve_kelly(_inputs(tail_index=1.2))
    thin = solve_kelly(_inputs(tail_index=3.0))
    assert fat.f_star >= thin.f_star
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_kelly.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.flow.kelly'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/flow/kelly.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_kelly.py -v`
Expected: 7 passed. This test module is the slowest in the suite (Monte Carlo); if it exceeds ~10s, reduce `trials`/`trades_per_path` in the test fixtures only, never in the defaults.

- [ ] **Step 5: Commit**

```bash
git add arena/flow/kelly.py tests/test_flow_kelly.py
git commit -m "feat: ruin-constrained heavy-tailed Kelly sizing calculator"
```

---

### Task 6: Jito tip advisor

**Files:**
- Create: `arena/flow/tips.py`
- Test: `tests/test_flow_tips.py`

**Interfaces:**
- Consumes: `httpx.AsyncClient` (caller-supplied, matching the existing `arena/prices.py` pattern)
- Produces:
  - `@dataclass TipFloor: p25: float; p50: float; p75: float; p95: float; p99: float` (SOL)
  - `class TipLookupError(Exception)`
  - `async fetch_tips(client: httpx.AsyncClient) -> TipFloor`
  - `recommend(tips: TipFloor, aggressiveness: str) -> float` — `"low"`→p50, `"normal"`→p75, `"high"`→p95

Endpoint: `https://bundles.jito.wtf/api/v1/bundles/tip_floor` — free, no key, returns a one-element list with `landed_tips_{25,50,75,95,99}th_percentile` in SOL.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_tips.py
import httpx
import pytest

from arena.flow.tips import TipLookupError, fetch_tips, recommend

PAYLOAD = [{
    "time": "2026-08-02T00:51:00+00:00",
    "landed_tips_25th_percentile": 1e-6,
    "landed_tips_50th_percentile": 1e-6,
    "landed_tips_75th_percentile": 1.598e-6,
    "landed_tips_95th_percentile": 0.0005,
    "landed_tips_99th_percentile": 0.00185,
    "ema_landed_tips_50th_percentile": 1.93e-6,
}]


def _client(response):
    def handler(request):
        return response
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_parses_percentiles():
    async with _client(httpx.Response(200, json=PAYLOAD)) as c:
        tips = await fetch_tips(c)
    assert tips.p50 == 1e-6
    assert tips.p95 == 0.0005
    assert tips.p99 == 0.00185


async def test_http_error_raises_lookup_error():
    async with _client(httpx.Response(503)) as c:
        with pytest.raises(TipLookupError):
            await fetch_tips(c)


async def test_empty_list_raises_lookup_error():
    async with _client(httpx.Response(200, json=[])) as c:
        with pytest.raises(TipLookupError):
            await fetch_tips(c)


async def test_missing_field_raises_lookup_error():
    async with _client(httpx.Response(200, json=[{"time": "x"}])) as c:
        with pytest.raises(TipLookupError):
            await fetch_tips(c)


async def test_recommendation_levels_are_ordered():
    async with _client(httpx.Response(200, json=PAYLOAD)) as c:
        tips = await fetch_tips(c)
    assert recommend(tips, "low") <= recommend(tips, "normal") <= recommend(tips, "high")


async def test_unknown_aggressiveness_falls_back_to_p75():
    async with _client(httpx.Response(200, json=PAYLOAD)) as c:
        tips = await fetch_tips(c)
    assert recommend(tips, "nonsense") == tips.p75
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_tips.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.flow.tips'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/flow/tips.py
"""Live Jito landed-tip percentiles — free, no API key.

Scope note: Coin Arena is advisory. The user types a number into their own
terminal, whose fee logic sits between them and the block. This reports what is
currently landing; it cannot promise inclusion.
"""

from dataclasses import dataclass

import httpx

TIP_FLOOR_URL = "https://bundles.jito.wtf/api/v1/bundles/tip_floor"


class TipLookupError(Exception):
    pass


@dataclass
class TipFloor:
    p25: float
    p50: float
    p75: float
    p95: float
    p99: float


async def fetch_tips(client: httpx.AsyncClient) -> TipFloor:
    try:
        resp = await client.get(TIP_FLOOR_URL, timeout=10)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        raise TipLookupError(str(exc)) from None
    if not isinstance(body, list) or not body:
        raise TipLookupError("empty tip_floor response")
    row = body[0]
    try:
        return TipFloor(
            p25=float(row["landed_tips_25th_percentile"]),
            p50=float(row["landed_tips_50th_percentile"]),
            p75=float(row["landed_tips_75th_percentile"]),
            p95=float(row["landed_tips_95th_percentile"]),
            p99=float(row["landed_tips_99th_percentile"]))
    except (KeyError, TypeError, ValueError):
        raise TipLookupError("malformed tip_floor response") from None


def recommend(tips: TipFloor, aggressiveness: str) -> float:
    return {"low": tips.p50, "normal": tips.p75,
            "high": tips.p95}.get(aggressiveness, tips.p75)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_tips.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add arena/flow/tips.py tests/test_flow_tips.py
git commit -m "feat: Jito landed-tip percentile advisor"
```

---

### Task 7: pump.fun TradeEvent decoder

**Files:**
- Create: `arena/stream/__init__.py` (empty)
- Create: `arena/stream/decode.py`
- Test: `tests/test_stream_decode.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `@dataclass TradeEvent: mint: str; sol: float; tokens: float; is_buy: bool; user: str; ts: int; v_sol: float; v_tok: float; price: float`
  - `decode_trade_event(payload_b64: str) -> TradeEvent | None`
  - `event_from_logs(logs: list[str]) -> TradeEvent | None`
  - `MIN_EVENT_BYTES: int = 113`

**Layout:** after an 8-byte discriminator — `mint` Pubkey(32), `solAmount` u64, `tokenAmount` u64, `isBuy` bool(1), `user` Pubkey(32), `timestamp` i64, `virtualSolReserves` u64, `virtualTokenReserves` u64. Total 113 bytes. **Newer program versions append extra fields — parse the 113-byte prefix and ignore any trailing bytes.** Do not validate the discriminator (it changes between IDL revisions); gate on the log line instead.

Units: SOL has 9 decimals, pump.fun tokens have 6. `price = (v_sol/1e9) / (v_tok/1e6)` in SOL per token.

Base58 encoding of pubkeys must be done without a new dependency — implement a small encoder.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stream_decode.py
import base64
import struct

from arena.stream.decode import decode_trade_event, event_from_logs

MINT = bytes(range(32))
USER = bytes(range(32, 64))


def _payload(sol=1_500_000_000, tokens=2_000_000_000, is_buy=True,
             v_sol=30_000_000_000, v_tok=1_000_000_000_000, extra=b""):
    return base64.b64encode(
        b"\x00" * 8 + MINT + struct.pack("<QQ?", sol, tokens, is_buy) + USER
        + struct.pack("<qQQ", 1_754_000_000, v_sol, v_tok) + extra).decode()


def test_decodes_all_fields():
    ev = decode_trade_event(_payload())
    assert ev is not None
    assert ev.is_buy is True
    assert abs(ev.sol - 1.5) < 1e-9
    assert abs(ev.tokens - 2000.0) < 1e-6
    assert ev.ts == 1_754_000_000
    assert len(ev.mint) >= 32  # base58 of a 32-byte key


def test_price_uses_sol_and_token_decimals():
    ev = decode_trade_event(_payload(v_sol=30_000_000_000, v_tok=1_000_000_000_000))
    # (30e9/1e9) / (1e12/1e6) = 30 / 1e6 = 3e-5 SOL per token
    assert abs(ev.price - 3e-5) < 1e-12


def test_tolerates_trailing_fields_from_newer_program_versions():
    ev = decode_trade_event(_payload(extra=b"\x01" * 48))
    assert ev is not None
    assert abs(ev.sol - 1.5) < 1e-9


def test_sell_flag_decodes():
    assert decode_trade_event(_payload(is_buy=False)).is_buy is False


def test_short_payload_returns_none():
    assert decode_trade_event(base64.b64encode(b"\x00" * 40).decode()) is None


def test_garbage_base64_returns_none():
    assert decode_trade_event("!!!not base64!!!") is None


def test_zero_reserves_returns_none():
    assert decode_trade_event(_payload(v_tok=0)) is None


def test_event_from_logs_requires_a_trade_instruction():
    logs = ["Program log: Instruction: Create", f"Program data: {_payload()}"]
    assert event_from_logs(logs) is None


def test_event_from_logs_picks_the_trade_payload():
    logs = ["Program log: Instruction: Buy",
            "Program data: c2hvcnQ=",
            f"Program data: {_payload()}"]
    ev = event_from_logs(logs)
    assert ev is not None and ev.is_buy is True


def test_event_from_logs_returns_none_without_payload():
    assert event_from_logs(["Program log: Instruction: Sell"]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_stream_decode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.stream'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/stream/__init__.py
```

```python
# arena/stream/decode.py
"""Decode pump.fun TradeEvent payloads emitted as `Program data:` log lines.

The 113-byte prefix layout is stable across program versions; newer versions
append fields, so we parse the prefix and ignore the tail. The discriminator is
deliberately NOT validated — it changes between IDL revisions — so callers gate
on the `Instruction: Buy`/`Sell` log line instead.
"""

import base64
import struct
from dataclasses import dataclass

MIN_EVENT_BYTES = 113
_HEADER = 8
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRADE_MARKERS = ("Instruction: Buy", "Instruction: Sell")

SOL_DECIMALS = 1e9
TOKEN_DECIMALS = 1e6


@dataclass
class TradeEvent:
    mint: str
    sol: float
    tokens: float
    is_buy: bool
    user: str
    ts: int
    v_sol: float
    v_tok: float
    price: float


def _b58(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + out


def decode_trade_event(payload_b64: str) -> TradeEvent | None:
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception:
        return None
    if len(raw) < MIN_EVENT_BYTES:
        return None
    o = _HEADER
    mint = raw[o:o + 32]
    o += 32
    sol, tokens, is_buy = struct.unpack_from("<QQ?", raw, o)
    o += 17
    user = raw[o:o + 32]
    o += 32
    ts, v_sol, v_tok = struct.unpack_from("<qQQ", raw, o)
    if v_sol <= 0 or v_tok <= 0:
        return None
    price = (v_sol / SOL_DECIMALS) / (v_tok / TOKEN_DECIMALS)
    return TradeEvent(mint=_b58(mint), sol=sol / SOL_DECIMALS,
                      tokens=tokens / TOKEN_DECIMALS, is_buy=bool(is_buy),
                      user=_b58(user), ts=ts, v_sol=v_sol / SOL_DECIMALS,
                      v_tok=v_tok / TOKEN_DECIMALS, price=price)


def event_from_logs(logs: list[str]) -> TradeEvent | None:
    """Return the trade event from a log array, or None if this transaction
    was not a buy/sell."""
    if not any(m in line for line in logs for m in _TRADE_MARKERS):
        return None
    for line in logs:
        marker = "Program data: "
        if marker in line:
            event = decode_trade_event(line.split(marker, 1)[1].strip())
            if event is not None:
                return event
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stream_decode.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add arena/stream/__init__.py arena/stream/decode.py tests/test_stream_decode.py
git commit -m "feat: pump.fun TradeEvent Borsh decoder with version tolerance"
```

---

### Task 8: Bounded tape buffer

**Files:**
- Create: `arena/stream/tape.py`
- Test: `tests/test_stream_tape.py`

**Interfaces:**
- Consumes: `QME_TAPE_MAXLEN`, `QME_FIT_WINDOW_EVENTS`, `QME_FIT_WINDOW_SECONDS` from `arena.thresholds`
- Produces:
  - `@dataclass TapeEvent: ts: float; is_buy: bool; sol: float; price: float | None`
  - `class Tape`:
    - `__init__(self, maxlen: int = QME_TAPE_MAXLEN)`
    - `append(self, event: TapeEvent) -> None`
    - `__len__(self) -> int`
    - `window_times(self, now: float) -> list[float]`
    - `window_prices(self, now: float) -> list[tuple[float, float]]`
    - `clear(self) -> None`
    - `buy_share(self, now: float) -> float | None`

`window_times`/`window_prices` return the last `QME_FIT_WINDOW_EVENTS` events that are also within `QME_FIT_WINDOW_SECONDS` of `now`. `window_prices` drops events with `price is None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stream_tape.py
from arena.stream.tape import Tape, TapeEvent
from arena.thresholds import QME_FIT_WINDOW_EVENTS, QME_FIT_WINDOW_SECONDS


def _ev(ts, price=1.0, is_buy=True, sol=0.1):
    return TapeEvent(ts=ts, is_buy=is_buy, sol=sol, price=price)


def test_ring_buffer_drops_oldest_beyond_maxlen():
    tape = Tape(maxlen=10)
    for i in range(25):
        tape.append(_ev(float(i)))
    assert len(tape) == 10
    assert tape.window_times(now=24.0)[0] == 15.0


def test_window_excludes_events_older_than_the_time_window():
    tape = Tape()
    tape.append(_ev(0.0))
    tape.append(_ev(QME_FIT_WINDOW_SECONDS + 50.0))
    times = tape.window_times(now=QME_FIT_WINDOW_SECONDS + 50.0)
    assert times == [QME_FIT_WINDOW_SECONDS + 50.0]


def test_window_caps_at_event_limit():
    tape = Tape(maxlen=5000)
    for i in range(QME_FIT_WINDOW_EVENTS + 100):
        tape.append(_ev(i * 0.01))
    now = (QME_FIT_WINDOW_EVENTS + 99) * 0.01
    assert len(tape.window_times(now)) == QME_FIT_WINDOW_EVENTS


def test_window_prices_drops_none_prices():
    tape = Tape()
    tape.append(_ev(0.0, price=None))
    tape.append(_ev(1.0, price=2.0))
    assert tape.window_prices(now=1.0) == [(1.0, 2.0)]


def test_window_times_are_ascending():
    tape = Tape()
    for i in range(50):
        tape.append(_ev(float(i)))
    times = tape.window_times(now=49.0)
    assert times == sorted(times)


def test_buy_share_reports_fraction_of_buys():
    tape = Tape()
    for i in range(4):
        tape.append(_ev(float(i), is_buy=i < 3))
    assert abs(tape.buy_share(now=3.0) - 0.75) < 1e-9


def test_buy_share_none_when_empty():
    assert Tape().buy_share(now=0.0) is None


def test_clear_empties_the_tape():
    tape = Tape()
    tape.append(_ev(0.0))
    tape.clear()
    assert len(tape) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_stream_tape.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.stream.tape'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/stream/tape.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stream_tape.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add arena/stream/tape.py tests/test_stream_tape.py
git commit -m "feat: bounded per-mint tape buffer with fit windows"
```

---

### Task 9: Helius logsSubscribe client

**Files:**
- Create: `arena/stream/subscribe.py`
- Modify: `pyproject.toml` (add `websockets` to `dependencies`)
- Test: `tests/test_stream_subscribe.py`

**Interfaces:**
- Consumes: `event_from_logs` from `arena.stream.decode`; `TapeEvent` from `arena.stream.tape`
- Produces:
  - `subscription_payload(mint: str) -> dict`
  - `ws_url(key: str) -> str`
  - `parse_notification(message: str, now: float) -> TapeEvent | None`
  - `class Disconnected(Exception)`
  - `async watch(key: str, mint: str, on_event, on_disconnect, on_reconnect, stop, connect=None, clock=time.monotonic) -> None`

`connect` is injectable so tests drive a fake socket with no network. `stop` is an object with `.is_set() -> bool`. Reconnect uses exponential backoff capped at 30 s. Any socket exception calls `on_disconnect()` before retrying, and `on_reconnect()` after a successful resubscribe.

**Why the callbacks matter:** for this engine, absence of trades *is* the signal. A silently dead socket is indistinguishable from a coin going quiet, so disconnection must propagate to the UI immediately rather than leaving stale numbers on screen.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stream_subscribe.py
import base64
import json
import struct

from arena.stream.subscribe import (parse_notification, subscription_payload,
                                    watch, ws_url)


def _payload():
    return base64.b64encode(
        b"\x00" * 8 + bytes(range(32)) + struct.pack("<QQ?", 10**9, 10**9, True)
        + bytes(range(32, 64))
        + struct.pack("<qQQ", 1_754_000_000, 30 * 10**9, 10**12)).decode()


def _notification(logs):
    return json.dumps({
        "jsonrpc": "2.0", "method": "logsNotification",
        "params": {"result": {"value": {"signature": "sig", "err": None,
                                        "logs": logs}}}})


class FakeSocket:
    """Yields queued messages then raises to simulate a dropped connection."""

    def __init__(self, messages, fail_after=True):
        self.messages = list(messages)
        self.fail_after = fail_after
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        if self.fail_after:
            raise ConnectionError("socket closed")
        raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class Stop:
    def __init__(self, after=1):
        self.calls = 0
        self.after = after

    def is_set(self):
        self.calls += 1
        return self.calls > self.after


def test_ws_url_uses_helius_mainnet_and_key():
    url = ws_url("KEY123")
    assert url.startswith("wss://")
    assert "KEY123" in url


def test_subscription_payload_targets_the_mint():
    payload = subscription_payload("MintABC")
    assert payload["method"] == "logsSubscribe"
    assert payload["params"][0] == {"mentions": ["MintABC"]}
    assert payload["params"][1]["commitment"] == "processed"


def test_parse_notification_extracts_a_buy():
    msg = _notification(["Program log: Instruction: Buy",
                         f"Program data: {_payload()}"])
    event = parse_notification(msg, now=123.0)
    assert event is not None
    assert event.ts == 123.0  # locally stamped arrival time
    assert event.is_buy is True
    assert event.price > 0


def test_parse_notification_ignores_non_trade_logs():
    msg = _notification(["Program log: Instruction: Create"])
    assert parse_notification(msg, now=1.0) is None


def test_parse_notification_ignores_failed_transactions():
    msg = json.dumps({"params": {"result": {"value": {
        "signature": "s", "err": {"InstructionError": [0, "X"]},
        "logs": ["Program log: Instruction: Buy",
                 f"Program data: {_payload()}"]}}}})
    assert parse_notification(msg, now=1.0) is None


def test_parse_notification_ignores_subscription_confirmation():
    assert parse_notification(json.dumps({"result": 42, "id": 1}), now=1.0) is None


def test_parse_notification_survives_garbage():
    assert parse_notification("not json", now=1.0) is None


async def test_watch_sends_subscription_and_emits_events():
    msg = _notification(["Program log: Instruction: Buy",
                         f"Program data: {_payload()}"])
    socket = FakeSocket([msg], fail_after=False)
    events, states = [], []

    async def connect(url):
        return socket

    await watch("KEY", "MintABC", on_event=events.append,
                on_disconnect=lambda: states.append("down"),
                on_reconnect=lambda: states.append("up"),
                stop=Stop(after=1), connect=connect)

    assert len(events) == 1
    sent = json.loads(socket.sent[0])
    assert sent["params"][0] == {"mentions": ["MintABC"]}


async def test_watch_reports_disconnect_then_reconnect():
    socket_a = FakeSocket([], fail_after=True)
    socket_b = FakeSocket([], fail_after=False)
    sockets = [socket_a, socket_b]
    states = []

    async def connect(url):
        return sockets.pop(0)

    await watch("KEY", "M", on_event=lambda e: None,
                on_disconnect=lambda: states.append("down"),
                on_reconnect=lambda: states.append("up"),
                stop=Stop(after=2), connect=connect)

    assert "down" in states
    assert states.index("down") < states.index("up")


async def test_watch_stops_when_stop_is_set():
    calls = {"n": 0}

    async def connect(url):
        calls["n"] += 1
        return FakeSocket([], fail_after=False)

    class AlwaysStop:
        def is_set(self):
            return True

    await watch("KEY", "M", on_event=lambda e: None,
                on_disconnect=lambda: None, on_reconnect=lambda: None,
                stop=AlwaysStop(), connect=connect)
    assert calls["n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_stream_subscribe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.stream.subscribe'`

- [ ] **Step 3: Write minimal implementation**

Modify `pyproject.toml` line 5:

```toml
dependencies = ["httpx", "rich", "websockets"]
```

Install it:

```bash
.venv/bin/pip install -e '.[gui,dev]'
```

Create `arena/stream/subscribe.py`:

```python
"""Helius logsSubscribe client for a single mint.

Disconnection is a first-class event, not an error to swallow: for this engine
an absence of trades IS the signal, so a silently dead socket looks exactly
like a coin going quiet. on_disconnect fires immediately so the UI can suppress
stale numbers.
"""

import asyncio
import json
import logging
import time

from arena.stream.decode import event_from_logs
from arena.stream.tape import TapeEvent

log = logging.getLogger(__name__)

HELIUS_WS = "wss://mainnet.helius-rpc.com/?api-key={key}"
BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0
PING_INTERVAL_S = 15
PING_TIMEOUT_S = 10


class Disconnected(Exception):
    pass


def ws_url(key: str) -> str:
    return HELIUS_WS.format(key=key)


def subscription_payload(mint: str) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
            "params": [{"mentions": [mint]}, {"commitment": "processed"}]}


def parse_notification(message: str, now: float) -> TapeEvent | None:
    """Locally stamped arrival time — carries 50-200ms of network jitter, so
    nothing downstream may claim sub-second precision."""
    try:
        body = json.loads(message)
        value = body["params"]["result"]["value"]
    except Exception:
        return None
    if value.get("err") is not None:
        return None
    trade = event_from_logs(value.get("logs") or [])
    if trade is None:
        return None
    return TapeEvent(ts=now, is_buy=trade.is_buy, sol=trade.sol,
                     price=trade.price)


async def _default_connect(url: str):
    import websockets
    return await websockets.connect(url, ping_interval=PING_INTERVAL_S,
                                    ping_timeout=PING_TIMEOUT_S)


async def watch(key: str, mint: str, on_event, on_disconnect, on_reconnect,
                stop, connect=None, clock=time.monotonic) -> None:
    connect = connect or _default_connect
    backoff = BACKOFF_START_S
    first = True
    while not stop.is_set():
        try:
            socket = await connect(ws_url(key))
            await socket.send(json.dumps(subscription_payload(mint)))
            if not first:
                on_reconnect()
            first = False
            backoff = BACKOFF_START_S
            async for message in socket:
                if stop.is_set():
                    return
                event = parse_notification(message, clock())
                if event is not None:
                    on_event(event)
        except Exception as exc:
            log.warning("stream dropped: %s", exc)
            on_disconnect()
            if stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stream_subscribe.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add arena/stream/subscribe.py pyproject.toml tests/test_stream_subscribe.py
git commit -m "feat: Helius logsSubscribe stream with backoff and disconnect signalling"
```

---

### Task 10: Funding entropy (pure)

**Files:**
- Create: `arena/checks/entropy.py`
- Test: `tests/test_check_entropy.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `@dataclass EntropyResult: h: float; h_norm: float; n_buyers: int; n_roots: int; largest_share: float; largest_root: str | None`
  - `funding_entropy(roots: dict[str, str]) -> EntropyResult | None` — maps buyer address → root funding source. `None` for fewer than 2 buyers.
  - `describe(result: EntropyResult) -> str` — the plain-language sentence.

`h = −Σ pᵢ ln pᵢ`, `h_norm = h / ln(n_buyers)` (defined as `1.0` when every buyer has a distinct root and `n_buyers > 1`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_entropy.py
import math

from arena.checks.entropy import describe, funding_entropy


def test_none_below_two_buyers():
    assert funding_entropy({"a": "r1"}) is None
    assert funding_entropy({}) is None


def test_fully_independent_buyers_give_maximum_entropy():
    roots = {f"b{i}": f"r{i}" for i in range(10)}
    r = funding_entropy(roots)
    assert abs(r.h - math.log(10)) < 1e-9
    assert abs(r.h_norm - 1.0) < 1e-9
    assert r.n_roots == 10


def test_single_source_gives_zero_entropy():
    roots = {f"b{i}": "whale" for i in range(20)}
    r = funding_entropy(roots)
    assert abs(r.h) < 1e-9
    assert abs(r.h_norm) < 1e-9
    assert r.largest_root == "whale"
    assert abs(r.largest_share - 1.0) < 1e-9


def test_mixed_case_lands_between():
    roots = {f"b{i}": ("whale" if i < 12 else f"r{i}") for i in range(15)}
    r = funding_entropy(roots)
    assert 0.0 < r.h_norm < 1.0
    assert r.largest_root == "whale"
    assert abs(r.largest_share - 12 / 15) < 1e-9
    assert r.n_buyers == 15


def test_describe_states_the_dominant_cluster():
    roots = {f"b{i}": ("whale" if i < 12 else f"r{i}") for i in range(15)}
    text = describe(funding_entropy(roots))
    assert "12 of 15" in text
    assert "0.2" in text or "0.3" in text  # normalised entropy is shown


def test_describe_for_independent_buyers():
    text = describe(funding_entropy({f"b{i}": f"r{i}" for i in range(6)}))
    assert "6 distinct" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_check_entropy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.checks.entropy'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/checks/entropy.py
"""Shannon entropy over the funding sources of a token's launch buyers.

H(F) = -sum p_i ln(p_i), where p_i is the share of launch buyers whose funds
trace back to root source i. Low entropy means one wallet funded many buyers —
a topological fact about the chain, not a probability. Resolving buyers to
roots is the network-bound half and lives in arena/funding_graph.py.
"""

import math
from collections import Counter
from dataclasses import dataclass


@dataclass
class EntropyResult:
    h: float
    h_norm: float
    n_buyers: int
    n_roots: int
    largest_share: float
    largest_root: str | None


def funding_entropy(roots: dict[str, str]) -> EntropyResult | None:
    n = len(roots)
    if n < 2:
        return None
    counts = Counter(roots.values())
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log(p)
    largest_root, largest_count = counts.most_common(1)[0]
    return EntropyResult(h=h, h_norm=h / math.log(n), n_buyers=n,
                         n_roots=len(counts),
                         largest_share=largest_count / n,
                         largest_root=largest_root)


def describe(result: EntropyResult) -> str:
    biggest = round(result.largest_share * result.n_buyers)
    if result.n_roots == result.n_buyers:
        return (f"{result.n_buyers} launch buyers funded from "
                f"{result.n_roots} distinct sources — H̃ = "
                f"{result.h_norm:.2f}")
    return (f"{biggest} of {result.n_buyers} launch buyers trace back to one "
            f"wallet — H̃ = {result.h_norm:.2f}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_check_entropy.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add arena/checks/entropy.py tests/test_check_entropy.py
git commit -m "feat: funding-entropy computation over buyer root sources"
```

---

### Task 11: Funding-graph walk with root detection and cache

**Files:**
- Create: `arena/funding_graph.py`
- Modify: `arena/store.py` (add `funding_edges` to `SCHEMA`, add two methods)
- Modify: `arena/thresholds.py` (append walk constants)
- Test: `tests/test_funding_graph.py`

**Interfaces:**
- Consumes: `RpcClient.enhanced_txs` from `arena.rpc`; `Store` from `arena.store`
- Produces:
  - `CEX_ADDRESSES: frozenset[str]`
  - `is_root_like(address: str, tx_count: int) -> bool`
  - `async funder_of(rpc, store, address: str) -> tuple[str | None, bool]` — returns `(parent_address, is_root)`; caches to `funding_edges`
  - `async resolve_roots(rpc, store, buyers: list[str], hops: int = FUNDING_GRAPH_HOPS) -> dict[str, str]`
  - `Store.cached_edge(child: str) -> tuple[str | None, bool] | None`
  - `Store.save_edge(child: str, parent: str | None, is_root: bool) -> None`

**The correctness-critical rule:** a naive walk collapses every Coinbase-funded wallet into a single root, craters entropy, and screams "cabal" at a launch of genuinely independent buyers. The walk therefore stops at **root-like** nodes and counts each as its own distinct source. A wallet is root-like if it is in `CEX_ADDRESSES` **or** its transaction count exceeds `FUNDING_ROOT_TX_COUNT`. A relay wallet has tens of transactions; an exchange hot wallet has millions.

A buyer whose funder cannot be resolved maps to **itself** — an unresolvable wallet is not evidence of coordination and must not be lumped with other unresolved wallets.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_funding_graph.py
from arena.checks.entropy import funding_entropy
from arena.funding_graph import (CEX_ADDRESSES, funder_of, is_root_like,
                                 resolve_roots)
from arena.rpc import RpcClient
from arena.store import Store
from arena.thresholds import FUNDING_PAGE_SIZE, FUNDING_ROOT_TX_COUNT
from tests.helpers import make_client


def _funding_tx(sender, receiver):
    return {"signature": f"{sender}->{receiver}", "timestamp": 100,
            "nativeTransfers": [{"fromUserAccount": sender,
                                 "toUserAccount": receiver,
                                 "amount": 500_000_000}]}


def test_known_cex_address_is_root_like():
    any_cex = next(iter(CEX_ADDRESSES))
    assert is_root_like(any_cex, tx_count=3) is True


def test_high_transaction_count_is_root_like():
    assert is_root_like("Whatever", FUNDING_ROOT_TX_COUNT + 1) is True


def test_ordinary_relay_wallet_is_not_root_like():
    assert is_root_like("Relay1", tx_count=30) is False


async def test_funder_of_returns_the_sending_wallet(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {"Buyer1": [_funding_tx("Relay1", "Buyer1")]}
    async with make_client(enhanced=enhanced) as c:
        parent, is_root = await funder_of(RpcClient(c, "k"), store, "Buyer1")
    assert parent == "Relay1"
    assert is_root is False
    store.close()


async def test_funder_of_uses_cache_on_second_call(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {"Buyer1": [_funding_tx("Relay1", "Buyer1")]}
    async with make_client(enhanced=enhanced) as c:
        rpc = RpcClient(c, "k")
        await funder_of(rpc, store, "Buyer1")
    # Second call with an RPC that would fail if actually used.
    async with make_client(enhanced={}) as c2:
        parent, _ = await funder_of(RpcClient(c2, "k"), store, "Buyer1")
    assert parent == "Relay1"
    store.close()


async def test_resolve_roots_collapses_a_cabal(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {f"B{i}": [_funding_tx("Relay1", f"B{i}")] for i in range(6)}
    enhanced["Relay1"] = [_funding_tx("Whale", "Relay1")]
    enhanced["Whale"] = []
    async with make_client(enhanced=enhanced) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store,
                                    [f"B{i}" for i in range(6)], hops=2)
    assert len(set(roots.values())) == 1
    result = funding_entropy(roots)
    assert result.h_norm < 0.01
    store.close()


async def test_cex_funded_buyers_stay_distinct(tmp_path):
    """The false-alarm trap: independent buyers all funded from one exchange
    must NOT collapse into a single root."""
    store = Store(tmp_path / "t.db")
    cex = next(iter(CEX_ADDRESSES))
    enhanced = {f"B{i}": [_funding_tx(cex, f"B{i}")] for i in range(6)}
    async with make_client(enhanced=enhanced) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store,
                                    [f"B{i}" for i in range(6)], hops=2)
    assert len(set(roots.values())) == 6
    assert funding_entropy(roots).h_norm > 0.99
    store.close()


async def test_busy_wallet_becomes_a_root_and_buyers_stay_distinct(tmp_path):
    """An unlisted aggregator with a huge signature count must behave like a
    CEX: buyers funded from it stay independent rather than collapsing."""
    store = Store(tmp_path / "t.db")
    busy = "BusyAggregator"
    enhanced = {f"B{i}": [_funding_tx(busy, f"B{i}")] for i in range(4)}
    # A full page of transactions triggers the signature count.
    enhanced[busy] = [_funding_tx("X", busy) for _ in range(FUNDING_PAGE_SIZE)]
    rpc_methods = {"getSignaturesForAddress":
                   [{"signature": f"s{i}"} for i in range(FUNDING_ROOT_TX_COUNT)]}
    async with make_client(enhanced=enhanced, rpc_methods=rpc_methods) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store,
                                    [f"B{i}" for i in range(4)], hops=2)
    assert len(set(roots.values())) == 4
    store.close()


async def test_moderately_active_wallet_is_not_a_root(tmp_path):
    """A relay wallet with a full page but few total signatures must still be
    followed through, so real cabals are not missed."""
    store = Store(tmp_path / "t.db")
    relay = "Relay1"
    enhanced = {"B0": [_funding_tx(relay, "B0")],
                relay: [_funding_tx("Whale", relay)
                        for _ in range(FUNDING_PAGE_SIZE)],
                "Whale": []}
    rpc_methods = {"getSignaturesForAddress":
                   [{"signature": f"s{i}"} for i in range(120)]}
    async with make_client(enhanced=enhanced, rpc_methods=rpc_methods) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B1"],
                                    hops=2)
    assert roots["B0"] == "Whale"
    store.close()


async def test_unresolvable_buyer_maps_to_itself(tmp_path):
    store = Store(tmp_path / "t.db")
    async with make_client(enhanced={"B0": [], "B1": []}) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B1"])
    assert roots["B0"] == "B0"
    assert roots["B1"] == "B1"
    store.close()


async def test_walk_stops_at_hop_limit(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {"B0": [_funding_tx("L1", "B0")],
                "L1": [_funding_tx("L2", "L1")],
                "L2": [_funding_tx("L3", "L2")],
                "L3": []}
    async with make_client(enhanced=enhanced) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B0x"],
                                    hops=2)
    assert roots["B0"] == "L2"  # two hops, not three
    store.close()


async def test_rpc_failure_does_not_crash_the_walk(tmp_path):
    store = Store(tmp_path / "t.db")
    async with make_client(enhanced={"B0": 500}) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B1"])
    assert roots["B0"] == "B0"
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_funding_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.funding_graph'`

- [ ] **Step 3: Write minimal implementation**

Append to `arena/thresholds.py`:

```python
FUNDING_GRAPH_HOPS = 2
FUNDING_GRAPH_MAX_BUYERS = 20   # cap API calls: 20 buyers x 2 hops = 40 requests
FUNDING_ROOT_TX_COUNT = 1000    # at/above this a wallet is an exchange/aggregator
FUNDING_PAGE_SIZE = 100         # enhanced_txs page; a full page triggers a count
```

Add to `arena/store.py` `SCHEMA` (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS funding_edges (
    child TEXT PRIMARY KEY,
    parent TEXT,
    is_root INTEGER NOT NULL DEFAULT 0,
    resolved_ts INTEGER NOT NULL
);
```

Add to `arena/store.py` `Store`:

```python
    def cached_edge(self, child: str) -> tuple[str | None, bool] | None:
        row = self.conn.execute(
            "SELECT parent, is_root FROM funding_edges WHERE child = ?",
            (child,)).fetchone()
        return (row["parent"], bool(row["is_root"])) if row else None

    def save_edge(self, child: str, parent: str | None, is_root: bool) -> None:
        self.conn.execute(
            "INSERT INTO funding_edges (child, parent, is_root, resolved_ts) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(child) DO UPDATE SET "
            "parent = excluded.parent, is_root = excluded.is_root, "
            "resolved_ts = excluded.resolved_ts",
            (child, parent, int(is_root), int(time.time())))
        self.conn.commit()
```

Create `arena/funding_graph.py`:

```python
"""Backward k-hop walk from launch buyers to their funding roots.

THE TRAP THIS AVOIDS: a naive walk collapses every Coinbase-funded wallet into
one root, craters entropy, and reports "cabal" on a launch full of genuinely
independent retail buyers. The walk therefore terminates at root-like nodes —
known exchange addresses, or wallets with implausibly many transactions — and
counts each as its own distinct source. A relay wallet has tens of
transactions; an exchange hot wallet has millions.

Cost: FUNDING_GRAPH_MAX_BUYERS x FUNDING_GRAPH_HOPS requests, which is why the
caller exposes this behind an explicit button rather than running it on every
scan. Resolved edges are cached in SQLite.

Approximation, stated plainly: we take the earliest incoming SOL transfer
visible in the most recent FUNDING_PAGE_SIZE transactions rather than paging to
the true first transaction. For a fresh sniper wallet — which has a handful of
transactions — that IS the funding transaction. Wallets busy enough for the
approximation to break are exactly the wallets the root rule bails out on.
"""

import logging

from arena.rpc import RpcClient
from arena.store import Store
from arena.thresholds import (FUNDING_GRAPH_HOPS, FUNDING_GRAPH_MAX_BUYERS,
                              FUNDING_PAGE_SIZE, FUNDING_ROOT_TX_COUNT)

log = logging.getLogger(__name__)

# Exchange hot wallets and well-known aggregators. Each is a root: many
# unrelated users withdraw from the same address, so shared provenance here is
# not evidence of coordination.
CEX_ADDRESSES = frozenset({
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",   # Binance
    "2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S",   # Coinbase 1
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS",   # Coinbase 2
    "AC5RDfQFmDS1deWZos921JfqscXdByf8BKHs5ACWjtW2",   # Bybit
    "u6PJ8DtQuPFnfmwHbGFULQ4u4EgjDiyYKjVEsynXq2w",    # Gate.io
    "GJRs4FwHtemZ5ZE9x3FNvJ8TMwitKTh21yxdRPqn7npE",   # Kraken
})


def is_root_like(address: str, tx_count: int) -> bool:
    return address in CEX_ADDRESSES or tx_count >= FUNDING_ROOT_TX_COUNT


async def funder_of(rpc: RpcClient, store: Store,
                    address: str) -> tuple[str | None, bool]:
    """(parent, parent_is_root). Parent is None when unresolvable."""
    cached = store.cached_edge(address)
    if cached is not None:
        return cached
    if address in CEX_ADDRESSES:
        store.save_edge(address, None, True)
        return None, True
    try:
        txs = await rpc.enhanced_txs(address, limit=FUNDING_PAGE_SIZE)
    except Exception as exc:
        log.warning("funding hop failed for %s: %s", address, exc)
        return None, False
    # A full page means the wallet MIGHT be busy enough to be an aggregator.
    # Only then is the extra signature count worth an API call; a fresh sniper
    # wallet has a handful of transactions and never pays for this.
    if len(txs) >= FUNDING_PAGE_SIZE:
        try:
            sigs = await rpc.rpc("getSignaturesForAddress",
                                 [address, {"limit": FUNDING_ROOT_TX_COUNT}])
        except Exception as exc:
            log.warning("signature count failed for %s: %s", address, exc)
            sigs = []
        if is_root_like(address, len(sigs or [])):
            store.save_edge(address, None, True)
            return None, True
    parent = None
    for tx in sorted(txs, key=lambda t: t.get("timestamp") or 0):
        for transfer in tx.get("nativeTransfers") or []:
            if (transfer.get("toUserAccount") == address
                    and transfer.get("fromUserAccount")):
                parent = transfer["fromUserAccount"]
                break
        if parent:
            break
    if parent is None:
        store.save_edge(address, None, False)
        return None, False
    parent_is_root = parent in CEX_ADDRESSES
    store.save_edge(address, parent, parent_is_root)
    return parent, parent_is_root


async def resolve_roots(rpc: RpcClient, store: Store, buyers: list[str],
                        hops: int = FUNDING_GRAPH_HOPS) -> dict[str, str]:
    """Map each buyer to its root funding source. An unresolvable buyer maps to
    ITSELF — not knowing where a wallet's money came from is not evidence that
    it shares a source with another unknown wallet."""
    roots: dict[str, str] = {}
    for buyer in buyers[:FUNDING_GRAPH_MAX_BUYERS]:
        current = buyer
        for _ in range(hops):
            parent, parent_is_root = await funder_of(rpc, store, current)
            if parent is None:
                break
            if parent_is_root:
                # The exchange is a root, but each withdrawal is independent —
                # attribute this buyer to itself, not to the exchange.
                current = buyer
                break
            current = parent
        roots[buyer] = current
    return roots
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_funding_graph.py tests/test_store.py -v`
Expected: all pass (existing store tests must still pass after the schema change)

- [ ] **Step 5: Commit**

```bash
git add arena/funding_graph.py arena/store.py arena/thresholds.py tests/test_funding_graph.py
git commit -m "feat: k-hop funding graph with CEX-aware root detection and edge cache"
```

---

### Task 12: macOS alerts

**Files:**
- Create: `arena/gui/alerts.py`
- Test: `tests/test_gui_alerts.py`

**Interfaces:**
- Consumes: nothing
- Produces: `fire_alert(title: str, body: str, runner=subprocess.run) -> None`

Plays `/System/Library/Sounds/Glass.aiff` via `afplay` and posts a notification via `osascript`. Both are macOS built-ins, so this adds no dependency. `runner` is injectable for tests. A failure in either channel must never propagate — a missing sound must not stop the notification, and neither must ever crash the watch loop.

Quoting matters: the body text comes from signal state, so double quotes must be escaped before being embedded in the AppleScript string.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gui_alerts.py
from arena.gui.alerts import fire_alert


class FakeRunner:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if self.fail_on and self.fail_on in args[0]:
            raise OSError("not found")
        return None


def test_plays_sound_and_posts_notification():
    runner = FakeRunner()
    fire_alert("EXIT", "cascade decay", runner=runner)
    commands = [c[0] for c in runner.calls]
    assert "afplay" in commands
    assert "osascript" in commands


def test_notification_carries_title_and_body():
    runner = FakeRunner()
    fire_alert("EXIT SIGNAL", "cascade decay", runner=runner)
    script = [c for c in runner.calls if c[0] == "osascript"][0][-1]
    assert "EXIT SIGNAL" in script
    assert "cascade decay" in script


def test_quotes_in_body_are_escaped():
    runner = FakeRunner()
    fire_alert("EXIT", 'he said "sell"', runner=runner)
    script = [c for c in runner.calls if c[0] == "osascript"][0][-1]
    assert '\\"sell\\"' in script


def test_sound_failure_does_not_block_notification():
    runner = FakeRunner(fail_on="afplay")
    fire_alert("EXIT", "reason", runner=runner)
    assert any(c[0] == "osascript" for c in runner.calls)


def test_notification_failure_is_swallowed():
    runner = FakeRunner(fail_on="osascript")
    fire_alert("EXIT", "reason", runner=runner)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.gui.alerts'`

- [ ] **Step 3: Write minimal implementation**

```python
# arena/gui/alerts.py
"""Sound + notification via macOS built-ins. No dependency, and it reaches the
user when Coin Arena is behind the trading terminal — which is the normal case.

Neither channel may ever raise: an alert failure must not kill a watch."""

import logging
import subprocess

log = logging.getLogger(__name__)

SOUND_PATH = "/System/Library/Sounds/Glass.aiff"


def fire_alert(title: str, body: str, runner=subprocess.run) -> None:
    try:
        runner(["afplay", SOUND_PATH], check=False, timeout=5)
    except Exception as exc:
        log.warning("alert sound failed: %s", exc)
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    try:
        runner(["osascript", "-e", script], check=False, timeout=5)
    except Exception as exc:
        log.warning("alert notification failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_alerts.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add arena/gui/alerts.py tests/test_gui_alerts.py
git commit -m "feat: macOS sound and notification alerts for exit signals"
```

---

### Task 13: Mode picker and routing

**Files:**
- Create: `arena/gui/views/mode_picker.py`
- Modify: `arena/gui/app.py`
- Modify: `arena/gui/views/check.py:82-87` (add a Back button to the header)
- Test: `tests/test_gui_mode_picker.py`
- Test: `tests/test_gui_app.py` (extend)

**Interfaces:**
- Consumes: `arena.gui.theme`, `arena.gui.logo.logo_image`
- Produces: `build_mode_picker(page, on_rug_check, on_qme) -> ft.View` with `route == "/modes"`

Routing after this task: splash → mode picker → (check | live). The check view gains a **Back** button at header index 0, shifting History to index 3 and Settings to index 4. **`tests/test_gui_check.py` and `tests/test_gui_app.py` index the header positionally and must be updated in the same commit.**

Layout contract for the picker view: `view.controls[0]` is a centered `Column`; `controls[0].controls[2]` is the Rug Pull Checker button and `controls[0].controls[3]` is the Quant Microstructure Engine button.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gui_mode_picker.py
from arena.gui.views.mode_picker import build_mode_picker


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _buttons(view):
    column = view.controls[0]
    return column.controls[2], column.controls[3]


def test_route_is_modes():
    view = build_mode_picker(FakePage(), on_rug_check=lambda: None,
                             on_qme=lambda: None)
    assert view.route == "/modes"


def test_offers_both_doors_with_exact_labels():
    view = build_mode_picker(FakePage(), on_rug_check=lambda: None,
                             on_qme=lambda: None)
    rug, qme = _buttons(view)
    assert rug.content.controls[0].value == "Rug Pull Checker"
    assert qme.content.controls[0].value == "Quant Microstructure Engine"


def test_rug_button_routes():
    clicked = {"flag": False}
    view = build_mode_picker(FakePage(),
                             on_rug_check=lambda: clicked.__setitem__("flag", True),
                             on_qme=lambda: None)
    _buttons(view)[0].on_click(None)
    assert clicked["flag"] is True


def test_qme_button_routes():
    clicked = {"flag": False}
    view = build_mode_picker(FakePage(), on_rug_check=lambda: None,
                             on_qme=lambda: clicked.__setitem__("flag", True))
    _buttons(view)[1].on_click(None)
    assert clicked["flag"] is True
```

Append to `tests/test_gui_app.py`:

```python
def test_splash_advances_to_mode_picker(monkeypatch):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    page = FakePage()
    main(page)
    FakeTimer.last_instance.fn()
    assert page.views[0].route == "/modes"


def test_mode_picker_routes_to_rug_check_and_back(monkeypatch, tmp_path):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    page = FakePage()
    main(page)
    FakeTimer.last_instance.fn()

    picker = page.views[0]
    picker.controls[0].controls[2].on_click(None)   # Rug Pull Checker
    assert page.views[0].route == "/"

    back_btn = page.views[0].controls[0].controls[0]
    back_btn.on_click(None)
    assert page.views[0].route == "/modes"


def test_mode_picker_routes_to_qme(monkeypatch, tmp_path):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    page = FakePage()
    main(page)
    FakeTimer.last_instance.fn()
    page.views[0].controls[0].controls[3].on_click(None)   # QME
    assert page.views[0].route == "/live"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_mode_picker.py tests/test_gui_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.gui.views.mode_picker'`

- [ ] **Step 3: Write minimal implementation**

Create `arena/gui/views/mode_picker.py`:

```python
import flet as ft

from arena.gui import theme
from arena.gui.logo import logo_image


def _door(title: str, subtitle: str, on_click) -> ft.FilledButton:
    return ft.FilledButton(
        width=380, height=76, bgcolor=theme.CYAN, on_click=lambda _: on_click(),
        content=ft.Column(
            spacing=2, alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(title, size=16, weight=ft.FontWeight.W_500,
                        color=theme.WHITE),
                ft.Text(subtitle, size=12, color=theme.WHITE, opacity=0.85),
            ]))


def build_mode_picker(page: ft.Page, on_rug_check, on_qme) -> ft.View:
    return ft.View(
        route="/modes",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=theme.PAD,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    logo_image(width=88),
                    ft.Text("Coin Arena", size=22, weight=ft.FontWeight.W_500,
                            color=theme.INK),
                    _door("Rug Pull Checker",
                          "Six checks on a coin before you buy", on_rug_check),
                    _door("Quant Microstructure Engine",
                          "Live exit signal for a coin you hold", on_qme),
                ])
        ])
```

Replace `arena/gui/app.py` entirely:

```python
import flet as ft

from arena.gui import theme
from arena.gui.views.check import build_check
from arena.gui.views.history import build_history
from arena.gui.views.live import build_live
from arena.gui.views.mode_picker import build_mode_picker
from arena.gui.views.settings import build_settings
from arena.gui.views.splash import build_splash


def main(page: ft.Page) -> None:
    page.title = "Coin Arena"
    page.window.bgcolor = theme.WHITE
    page.window.width = 640
    page.window.height = 640

    def show_modes():
        page.views.clear()
        page.views.append(build_mode_picker(page, on_rug_check=show_check,
                                            on_qme=show_live))
        page.update()

    def show_check():
        page.views.clear()
        page.views.append(build_check(page, on_open_settings=show_settings,
                                      on_open_history=show_history,
                                      on_back=show_modes))
        page.update()

    def show_live():
        page.views.clear()
        page.views.append(build_live(page, on_back=show_modes))
        page.update()

    def show_history():
        page.views.append(build_history(page, on_back=show_check))
        page.update()

    def show_settings():
        page.views.append(build_settings(page, on_back=show_check))
        page.update()

    def show_splash():
        page.views.clear()
        page.views.append(build_splash(page, on_done=show_modes))
        page.update()

    show_splash()
```

In `arena/gui/views/check.py`, change the signature and header:

```python
def build_check(page: ft.Page, on_open_settings, on_open_history,
                on_back) -> ft.View:
```

```python
    header = ft.Row([
        ft.TextButton("Back", on_click=lambda _: on_back()),
        ft.Text("Coin Arena", size=20, weight=ft.FontWeight.W_500, color=theme.INK),
        ft.Container(expand=True),
        ft.TextButton("History", on_click=lambda _: on_open_history()),
        ft.TextButton("Settings", on_click=lambda _: on_open_settings()),
    ])
```

In `tests/test_gui_check.py`, update the helpers and every `build_check(...)` call:

```python
def _settings_button(view):
    return view.controls[0].controls[4]


def _history_button(view):
    return view.controls[0].controls[3]
```

Every `build_check(page, on_open_settings=..., on_open_history=...)` call in that file gains `on_back=lambda: None`.

In `tests/test_gui_app.py`, `test_routing_splash_to_check_to_settings_and_back` must now click through the mode picker first and read Settings at header index 4:

```python
def test_routing_splash_to_check_to_settings_and_back(monkeypatch, tmp_path):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    page = FakePage()
    main(page)

    FakeTimer.last_instance.fn()
    assert page.views[0].route == "/modes"

    page.views[0].controls[0].controls[2].on_click(None)  # Rug Pull Checker
    assert page.views[0].route == "/"

    settings_btn = page.views[0].controls[0].controls[4]
    settings_btn.on_click(None)
    assert len(page.views) == 2
    assert page.views[-1].route == "/settings"

    back_btn = page.views[-1].controls[0].controls[0]
    back_btn.on_click(None)
    assert len(page.views) == 1
    assert page.views[0].route == "/"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_mode_picker.py tests/test_gui_app.py tests/test_gui_check.py -v`
Expected: all pass. This task depends on Task 14's `build_live`; if implementing strictly in order, create a two-line placeholder `arena/gui/views/live.py` returning `ft.View(route="/live")` and replace it in Task 14.

- [ ] **Step 5: Commit**

```bash
git add arena/gui/views/mode_picker.py arena/gui/app.py arena/gui/views/check.py tests/test_gui_mode_picker.py tests/test_gui_app.py tests/test_gui_check.py
git commit -m "feat: two-door mode picker routing to rug checker and QME"
```

---

### Task 14: QME live view and watch worker

**Files:**
- Create: `arena/gui/live_worker.py`
- Create: `arena/gui/views/live.py` (replacing the Task 13 placeholder)
- Test: `tests/test_gui_live_worker.py`
- Test: `tests/test_gui_live.py`

**Interfaces:**
- Consumes: `MINT_RE` from `arena.engine`; `Tape`, `TapeEvent` from `arena.stream.tape`; `watch` from `arena.stream.subscribe`; `SignalEngine`, `SignalState`, `SENSITIVITIES`, `DEFAULT_SENSITIVITY`, state constants from `arena.flow.signal`; `hazard_per_s` from `arena.flow.hazard`; `fire_alert` from `arena.gui.alerts`; `load_settings` from `arena.settings`; `QME_BASE_HAZARD_PCT_PER_HOUR`, `QME_REFIT_INTERVAL_S` from `arena.thresholds`
- Produces:
  - `class WatchHandle`: `.stop()`, `.is_set()`
  - `start_watch(mint, key, sensitivity, base_hazard_pct, on_state, watch_fn=None, clock=time.monotonic) -> WatchHandle`
  - `build_live(page, on_back) -> ft.View` with `route == "/live"`

`start_watch` runs the socket on a daemon thread with its own event loop (mirroring `arena/gui/scan_worker.py`), appends events to a `Tape`, re-evaluates the `SignalEngine` at most once per `QME_REFIT_INTERVAL_S`, and calls `on_state(SignalState)` from the worker thread. The view marshals back via `page.run_thread`, exactly as `check.py` does. `fire_alert` fires exactly once per EXIT latch, not on every subsequent state emission.

Layout contract for the live view: `view.controls[0]` is the header `Row` (Back, title, spacer, sensitivity `Dropdown`); `view.controls[1]` is a `Column` whose `controls[0]` is the input `Row` (mint field, Watch button) and whose `controls[1]` is the readout `Column`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gui_live_worker.py
from arena.flow.signal import DISCONNECTED, EXIT, WARMUP
from arena.gui.live_worker import WatchHandle, start_watch
from arena.stream.tape import TapeEvent


def test_handle_stop_sets_the_flag():
    handle = WatchHandle()
    assert handle.is_set() is False
    handle.stop()
    assert handle.is_set() is True


def _fake_watch(events, disconnect=False):
    async def watch_fn(key, mint, on_event, on_disconnect, on_reconnect, stop,
                       **kw):
        for e in events:
            on_event(e)
        if disconnect:
            on_disconnect()
    return watch_fn


def test_emits_warmup_for_a_thin_tape():
    states = []
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=states.append,
        watch_fn=_fake_watch([TapeEvent(ts=float(i), is_buy=True, sol=0.1,
                                        price=1.0) for i in range(5)]),
        clock=lambda: next(ticks))
    handle.join(timeout=5)
    assert states
    assert states[-1].state == WARMUP


def test_disconnect_emits_disconnected_with_no_numbers():
    states = []
    ticks = iter([float(i) for i in range(200)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="balanced", base_hazard_pct=20.0,
        on_state=states.append, watch_fn=_fake_watch([], disconnect=True),
        clock=lambda: next(ticks))
    handle.join(timeout=5)
    assert states[-1].state == DISCONNECTED
    assert states[-1].eta is None and states[-1].lam is None


def test_alert_fires_once_per_exit_latch(monkeypatch):
    import arena.gui.live_worker as worker_mod
    fired = []
    monkeypatch.setattr(worker_mod, "fire_alert",
                        lambda title, body: fired.append((title, body)))
    # Flat price + large assumed hazard forces the stopping rule to fire.
    # The clock advances 0.2s per event so a refit happens every 5th event
    # (QME_REFIT_INTERVAL_S = 1.0) — about 9 fits, not one per event.
    events = [TapeEvent(ts=i * 0.1, is_buy=True, sol=0.1, price=1.0)
              for i in range(45)]
    ticks = iter([i * 0.2 for i in range(400)])
    handle = start_watch(
        mint="M" * 44, key="K", sensitivity="early", base_hazard_pct=9000.0,
        on_state=lambda s: None, watch_fn=_fake_watch(events),
        clock=lambda: next(ticks))
    handle.join(timeout=10)
    assert len(fired) == 1
    assert fired[0][0] == "EXIT"
```

```python
# tests/test_gui_live.py
import arena.gui.views.live as live_mod
from arena.flow.signal import DISCONNECTED, EXIT, HEATING
from arena.flow.signal import SignalState
from arena.gui.views.live import build_live


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _input_row(view):
    return view.controls[1].controls[0]


def _readout(view):
    return view.controls[1].controls[1]


def _sensitivity(view):
    return view.controls[0].controls[3]


def test_route_is_live():
    assert build_live(FakePage(), on_back=lambda: None).route == "/live"


def test_back_button_routes():
    clicked = {"flag": False}
    view = build_live(FakePage(),
                      on_back=lambda: clicked.__setitem__("flag", True))
    view.controls[0].controls[0].on_click(None)
    assert clicked["flag"] is True


def test_invalid_mint_shows_error_without_starting_a_watch(monkeypatch):
    started = {"flag": False}
    monkeypatch.setattr(live_mod, "start_watch",
                        lambda **kw: started.__setitem__("flag", True))
    view = build_live(FakePage(), on_back=lambda: None)
    _input_row(view).controls[0].value = "notamint"
    _input_row(view).controls[1].on_click(None)
    assert started["flag"] is False
    assert "not a valid" in _readout(view).controls[0].value


def test_missing_key_explains_instead_of_watching(monkeypatch):
    started = {"flag": False}
    monkeypatch.setattr(live_mod, "start_watch",
                        lambda **kw: started.__setitem__("flag", True))
    monkeypatch.setattr(live_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": None})())
    view = build_live(FakePage(), on_back=lambda: None)
    _input_row(view).controls[0].value = "M" * 44
    _input_row(view).controls[1].on_click(None)
    assert started["flag"] is False
    assert "Helius key" in _readout(view).controls[0].value


def test_disconnected_state_hides_numbers_and_warns():
    view = build_live(FakePage(), on_back=lambda: None)
    live_mod.render_state(view, SignalState(DISCONNECTED, None, None, None,
                                            None, None, "socket disconnected"))
    text = " ".join(c.value for c in _readout(view).controls if hasattr(c, "value"))
    assert "DISCONNECTED" in text
    assert "not" in text.lower()  # e.g. "signal is not live"
    assert "η" not in text


def test_hazard_is_labelled_as_assumed():
    view = build_live(FakePage(), on_back=lambda: None)
    live_mod.render_state(view, SignalState(HEATING, 0.7, 0.8, 4.0, 5.0,
                                            0.001, "cascade alive"))
    text = " ".join(c.value for c in _readout(view).controls if hasattr(c, "value"))
    assert "assumed" in text.lower()


def test_sensitivity_dropdown_offers_three_presets():
    view = build_live(FakePage(), on_back=lambda: None)
    values = [o.key for o in _sensitivity(view).options]
    assert values == ["early", "balanced", "late"]
    assert _sensitivity(view).value == "balanced"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_live_worker.py tests/test_gui_live.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.gui.live_worker'`

- [ ] **Step 3: Write minimal implementation**

Create `arena/gui/live_worker.py`:

```python
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
```

Create `arena/gui/views/live.py`.

**Verify one API before writing this file:** the dropdown option class has been
renamed across Flet releases (`ft.dropdown.Option` vs `ft.DropdownOption`).
Check which exists in the installed version with:

```bash
.venv/bin/python -c "import flet as ft; print(hasattr(ft.dropdown, 'Option'), hasattr(ft, 'DropdownOption'))"
```

Use whichever is present, and keep `tests/test_gui_live.py`'s
`test_sensitivity_dropdown_offers_three_presets` consistent with it — the test
reads `.key` off each option, which both variants expose.

```python
import flet as ft

from arena.engine import MINT_RE
from arena.flow.signal import (COOLING, DISCONNECTED, EXIT, HEATING,
                               SENSITIVITIES, WARMUP)
from arena.gui import theme
from arena.gui.live_worker import start_watch
from arena.settings import load_settings
from arena.thresholds import QME_BASE_HAZARD_PCT_PER_HOUR

STATE_COLORS = {
    HEATING: theme.VERDICT_COLORS["NO_RED_FLAGS"],
    COOLING: theme.VERDICT_COLORS["CAUTION"],
    EXIT: theme.VERDICT_COLORS["AVOID"],
    WARMUP: theme.MUTED,
    DISCONNECTED: theme.VERDICT_COLORS["AVOID"],
}


def _readout(view):
    return view.controls[1].controls[1]


def render_state(view, state) -> None:
    """Render a SignalState into the view's readout column. Module-level so
    tests can drive it directly without a socket."""
    out = _readout(view)
    out.controls.clear()
    color = STATE_COLORS.get(state.state, theme.MUTED)
    out.controls.append(ft.Text(state.state, size=26,
                                weight=ft.FontWeight.W_500, color=color))
    if state.state == DISCONNECTED:
        out.controls.append(ft.Text(
            "Stream dropped — the signal is not live. No trades showing does "
            "NOT mean the coin is quiet.", size=13, color=color))
        return
    out.controls.append(ft.Text(state.reason, size=13, color=theme.MUTED))
    if state.eta is not None:
        out.controls.append(ft.Text(
            f"η = {state.eta:.2f} (peak {state.eta_peak:.2f})   "
            f"λ = {state.lam:.1f}/s (peak {state.lam_peak:.1f}/s)",
            size=13, color=theme.INK))
    if state.hold_drift is not None:
        out.controls.append(ft.Text(
            f"hold drift = {state.hold_drift * 3600:.2f}/hr  "
            f"(assumed crash hazard {QME_BASE_HAZARD_PCT_PER_HOUR:.0f}%/hr)",
            size=13, color=theme.INK))


def build_live(page: ft.Page, on_back) -> ft.View:
    mint_field = ft.TextField(label="Mint address you hold", width=380,
                              text_style=ft.TextStyle(font_family="monospace"))
    watch_btn = ft.FilledButton("Watch", bgcolor=theme.CYAN, color=theme.WHITE)
    sensitivity = ft.Dropdown(
        width=130, value="balanced",
        options=[ft.dropdown.Option(key=k, text=k.capitalize())
                 for k in ("early", "balanced", "late")])
    out = ft.Column(spacing=theme.GAP, width=520)
    handle_box: dict = {"handle": None}

    view = ft.View(
        route="/live",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([
                ft.TextButton("Back", on_click=lambda _: on_back()),
                ft.Text("Quant Microstructure Engine", size=18,
                        weight=ft.FontWeight.W_500, color=theme.INK),
                ft.Container(expand=True),
                sensitivity,
            ]),
            ft.Column([
                ft.Row([mint_field, watch_btn],
                       alignment=ft.MainAxisAlignment.CENTER),
                out,
            ], spacing=theme.PAD,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ])

    def error(message: str) -> None:
        out.controls.clear()
        out.controls.append(ft.Text(message, color=theme.VERDICT_COLORS["AVOID"]))
        page.update()

    def do_watch(_) -> None:
        if handle_box["handle"] is not None:
            handle_box["handle"].stop()
            handle_box["handle"] = None
        mint = (mint_field.value or "").strip()
        if not MINT_RE.match(mint):
            error("not a valid Solana mint address")
            return
        key = load_settings().helius_key
        if not key:
            error("The engine needs a free Helius key — add one in Settings.")
            return
        out.controls.clear()
        out.controls.append(ft.Text("connecting…", color=theme.MUTED))
        page.update()
        handle_box["handle"] = start_watch(
            mint=mint, key=key, sensitivity=sensitivity.value,
            base_hazard_pct=QME_BASE_HAZARD_PCT_PER_HOUR,
            on_state=lambda s: page.run_thread(_apply, s))

    def _apply(state) -> None:
        render_state(view, state)
        page.update()

    watch_btn.on_click = do_watch
    return view
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_live_worker.py tests/test_gui_live.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add arena/gui/live_worker.py arena/gui/views/live.py tests/test_gui_live_worker.py tests/test_gui_live.py
git commit -m "feat: QME live view with streaming exit signal and alerts"
```

---

### Task 15: Trace funding graph button, README, full-suite verification

**Files:**
- Modify: `arena/gui/views/check.py` (add the trace button and its result row)
- Create: `arena/gui/trace_worker.py`
- Modify: `README.md`
- Test: `tests/test_gui_trace.py`

**Interfaces:**
- Consumes: `resolve_roots` from `arena.funding_graph`; `funding_entropy`, `describe` from `arena.checks.entropy`; `Store`, `RpcClient`, `load_settings`
- Produces:
  - `run_trace(mint, buyers, settings, on_done, on_error, trace_fn=None) -> threading.Thread` in `arena/gui/trace_worker.py`, matching `scan_worker.run_scan`'s contract exactly (callbacks fire from the worker thread)

The button appears in the results column only when the scan produced a `bundles` finding containing `launch_buyers`, and only when a Helius key is set. Clicking it runs the walk off-thread and appends the `describe(...)` sentence to the results.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gui_trace.py
import arena.gui.views.check as check_mod
from arena.models import Finding, ScanResult


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _result_with_buyers(n=6):
    return ScanResult(
        mint="M" * 44, verdict="CAUTION",
        findings=[Finding("bundles", "PASS", "no bundling",
                          {"launch_buyers": n,
                           "buyers": [f"B{i}" for i in range(n)]})],
        unavailable=0, price_usd=None, symbol=None, duration_s=0.1)


def _results(view):
    return view.controls[1].controls[1]


def _render(monkeypatch, result, key="k"):
    monkeypatch.setattr(check_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": key})())
    monkeypatch.setattr(check_mod, "run_scan",
                        lambda mint, settings, on_done, on_error: on_done(result))
    page = FakePage()
    view = check_mod.build_check(page, on_open_settings=lambda: None,
                                 on_open_history=lambda: None,
                                 on_back=lambda: None)
    view.controls[1].controls[0].controls[0].value = "M" * 44
    view.controls[1].controls[0].controls[1].on_click(None)
    return view


def _trace_button(view):
    for control in _results(view).controls:
        if getattr(control, "content", None) == "Trace funding graph":
            return control
    return None


def test_trace_button_appears_when_buyers_are_known(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    assert _trace_button(view) is not None


def test_trace_button_absent_without_a_key(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers(), key=None)
    assert _trace_button(view) is None


def test_trace_button_absent_without_buyers(monkeypatch):
    result = ScanResult(mint="M" * 44, verdict="CAUTION",
                        findings=[Finding("bundles", "INFO", "unavailable", {})],
                        unavailable=1, price_usd=None, symbol=None,
                        duration_s=0.1)
    view = _render(monkeypatch, result)
    assert _trace_button(view) is None


def test_clicking_trace_appends_the_entropy_sentence(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error:
            on_done({f"B{i}": "whale" for i in range(6)}))
    _trace_button(view).on_click(None)
    texts = [c.value for c in _results(view).controls if hasattr(c, "value")]
    assert any("6 of 6" in t for t in texts)


def test_trace_failure_shows_a_redacted_message(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error:
            on_error(RuntimeError("boom api-key=SECRET")))
    _trace_button(view).on_click(None)
    texts = [c.value for c in _results(view).controls if hasattr(c, "value")]
    assert any(t.startswith("trace failed:") for t in texts)
    assert not any("SECRET" in t for t in texts)
    assert any("api-key=***" in t for t in texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_trace.py -v`
Expected: FAIL — `run_trace` does not exist in `arena.gui.views.check`

- [ ] **Step 3: Write minimal implementation**

First, `arena/checks/bundles.py` must expose the buyer list. Change its `data` dict (line 32) to:

```python
    data = {"max_buyers_one_slot": worst, "launch_buyers": len(all_buyers),
            "buyers": sorted(all_buyers)}
```

Create `arena/gui/trace_worker.py`:

```python
"""Runs the funding-graph walk off the UI thread. Same contract as
scan_worker.run_scan: callbacks fire FROM the worker thread."""

import asyncio
import threading
from typing import Callable

import httpx

from arena.funding_graph import resolve_roots
from arena.rpc import RpcClient
from arena.settings import Settings
from arena.store import Store


async def _trace_async(buyers: list[str], settings: Settings) -> dict[str, str]:
    store = Store()
    try:
        async with httpx.AsyncClient() as client:
            return await resolve_roots(RpcClient(client, settings.helius_key),
                                       store, buyers)
    finally:
        store.close()


def _default_trace(mint: str, buyers: list[str], settings: Settings) -> dict:
    return asyncio.run(_trace_async(buyers, settings))


def run_trace(mint: str, buyers: list[str], settings: Settings,
              on_done: Callable[[dict], None],
              on_error: Callable[[Exception], None],
              trace_fn=None) -> threading.Thread:
    fn = trace_fn or _default_trace

    def worker() -> None:
        try:
            on_done(fn(mint, buyers, settings))
        except Exception as exc:
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
```

In `arena/gui/views/check.py`, add imports:

```python
from arena.checks.entropy import describe, funding_entropy
from arena.gui.trace_worker import run_trace
```

At the end of `render(result)`, after the unavailable footer, append:

```python
        bundles = next((f for f in result.findings if f.check == "bundles"), None)
        buyers = (bundles.data.get("buyers") if bundles else None) or []
        if buyers and load_settings().helius_key:
            results.controls.append(ft.TextButton(
                "Trace funding graph",
                on_click=lambda _, b=buyers: do_trace(b)))

    def show_entropy(roots):
        entropy = funding_entropy(roots)
        results.controls.append(ft.Text(
            describe(entropy) if entropy else "not enough buyers to trace",
            size=13, color=theme.INK))
        page.update()

    def show_trace_error(exc):
        results.controls.append(ft.Text(f"trace failed: {redact(str(exc))}",
                                        size=13, color=theme.MUTED))
        page.update()

    def do_trace(buyers):
        results.controls.append(ft.Text("tracing funding graph…", size=13,
                                        color=theme.MUTED))
        page.update()
        run_trace(mint_field.value.strip(), buyers, load_settings(),
                  on_done=lambda r: page.run_thread(show_entropy, r),
                  on_error=lambda e: page.run_thread(show_trace_error, e))
```

Update `README.md`. Replace the opening description (lines 1–13) with:

```markdown
# Coin Arena 🐴

**Two tools for Solana meme coins.** On launch, pick one:

- **Rug Pull Checker** — paste a mint address, get six checks and a verdict
  before you buy.
- **Quant Microstructure Engine** — paste a mint you already hold and get a
  live exit signal computed from the coin's own trade stream.

## Rug Pull Checker

- 🔴 **AVOID** — a mechanical rug setup was found
- 🟡 **CAUTION** — a couple of warning signs
- 🟢 **NO RED FLAGS** — nothing obvious found *(not the same as "safe" — read the caveats)*

It checks six things a candlestick chart can't show you: whether the dev can
still mint or freeze the token, how concentrated the supply is, whether the
launch was bundled by one person across many wallets, the dev wallet's launch
history, who funded the dev, and basic vitals (age, holders, liquidity).

**Trace funding graph** (optional, needs a key): walks each launch buyer's
funding back two hops and reports the Shannon entropy of the sources. Low
entropy means one wallet funded many buyers. It runs only when you click it,
because it costs about 40 API calls.

## Quant Microstructure Engine

Paste a mint you hold and press **Watch**. Coin Arena opens a live stream of
that coin's trades and fits a Hawkes process to them — the model used for
earthquake aftershocks and order-flow bursts, where each event raises the
chance of the next.

Two things can trigger an **EXIT** alert (sound + notification):

1. **Cascade decay** — the branching ratio η and the trade intensity λ have
   both fallen well off their peaks and stayed there. The buying cascade is no
   longer feeding itself.
2. **Hazard exceeds drift** — the coin's estimated log-drift no longer
   compensates for the assumed risk of a sudden total loss.

The **assumed crash hazard** is exactly that: an assumption you set, not
something measured from data. The arithmetic on top of it is exact; the input
is a belief, and the app shows it as one.

Sensitivity (Early / Balanced / Late) controls how much decay is required and
for how long before the alert fires.

### What it does not do

- It does not predict which coin will pump.
- It does not trade, hold keys, or touch your wallet. Every number is advisory.
- It cannot see faster than the network: timestamps carry 50–200 ms of jitter,
  so nothing here is millisecond-accurate.
- It runs only while the window is open. Closing the app closes the socket.
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: every test passes, including all pre-existing tests. Then confirm the engine imports without the GUI extra:

Run: `.venv/bin/python -c "import arena.flow.signal, arena.stream.subscribe, arena.funding_graph; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add arena/gui/views/check.py arena/gui/trace_worker.py arena/checks/bundles.py README.md tests/test_gui_trace.py
git commit -m "feat: opt-in funding-graph trace button and README for both modes"
```

---

### Task 16: Sizing and tip panel

**Files:**
- Create: `arena/gui/sizing_worker.py`
- Create: `arena/gui/views/sizing.py`
- Modify: `arena/gui/views/live.py` (add a Sizing button at header index 4)
- Modify: `arena/gui/app.py` (route to the sizing view)
- Modify: `tests/test_gui_live.py` (every `build_live` call gains `on_open_sizing`)
- Test: `tests/test_gui_sizing.py`

**Interfaces:**
- Consumes: `KellyInputs`, `KellyResult`, `solve_kelly` from `arena.flow.kelly`; `TipFloor`, `fetch_tips`, `recommend` from `arena.flow.tips`
- Produces:
  - `run_kelly(inputs, on_done, on_error, solve_fn=None) -> threading.Thread`
  - `run_tips(on_done, on_error, fetch_fn=None) -> threading.Thread`
  - `build_sizing(page, on_back) -> ft.View` with `route == "/sizing"`
  - `build_live(page, on_back, on_open_sizing) -> ft.View` (signature change)

Kelly is Monte Carlo and takes a noticeable moment, so it runs off the UI thread on the same contract as `scan_worker.run_scan`.

Layout contract for the sizing view: `view.controls[0]` is the header `Row` (Back, title); `view.controls[1]` is a `Column` whose `controls[0..4]` are the five input `TextField`s, `controls[5]` is the button `Row` (Compute, Fetch live tips), and `controls[6]` is the output `Column`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gui_sizing.py
import arena.gui.views.sizing as sizing_mod
from arena.flow.kelly import KellyResult
from arena.flow.tips import TipFloor
from arena.gui.views.sizing import build_sizing


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _fields(view):
    return view.controls[1].controls[:5]


def _compute_button(view):
    return view.controls[1].controls[5].controls[0]


def _tips_button(view):
    return view.controls[1].controls[5].controls[1]


def _out(view):
    return view.controls[1].controls[6]


def _texts(view):
    return [c.value for c in _out(view).controls if hasattr(c, "value")]


def test_route_is_sizing():
    assert build_sizing(FakePage(), on_back=lambda: None).route == "/sizing"


def test_back_button_routes():
    clicked = {"flag": False}
    view = build_sizing(FakePage(),
                        on_back=lambda: clicked.__setitem__("flag", True))
    view.controls[0].controls[0].on_click(None)
    assert clicked["flag"] is True


def test_five_belief_inputs_have_defaults():
    view = build_sizing(FakePage(), on_back=lambda: None)
    assert len(_fields(view)) == 5
    assert all(f.value for f in _fields(view))


def test_compute_renders_fraction_and_sensitivity(monkeypatch):
    result = KellyResult(f_star=0.12, f_constrained=0.05, drawdown_prob=0.03,
                         sensitivity=[("half hit rate", 0.01),
                                      ("stated hit rate", 0.05),
                                      ("double hit rate", 0.14)])
    monkeypatch.setattr(sizing_mod, "run_kelly",
                        lambda inputs, on_done, on_error: on_done(result))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _compute_button(view).on_click(None)
    text = " ".join(_texts(view))
    assert "5.0%" in text            # f_constrained as a percentage
    assert "half hit rate" in text   # the sensitivity table is the point
    assert "double hit rate" in text


def test_compute_labels_the_numbers_as_beliefs(monkeypatch):
    result = KellyResult(0.1, 0.05, 0.02,
                         [("half hit rate", 0.01), ("stated hit rate", 0.05),
                          ("double hit rate", 0.1)])
    monkeypatch.setattr(sizing_mod, "run_kelly",
                        lambda inputs, on_done, on_error: on_done(result))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _compute_button(view).on_click(None)
    assert any("assumption" in t.lower() or "belief" in t.lower()
               for t in _texts(view))


def test_invalid_input_shows_an_error_without_computing(monkeypatch):
    called = {"flag": False}
    monkeypatch.setattr(sizing_mod, "run_kelly",
                        lambda **kw: called.__setitem__("flag", True))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _fields(view)[0].value = "not a number"
    _compute_button(view).on_click(None)
    assert called["flag"] is False
    assert any("number" in t.lower() for t in _texts(view))


def test_tips_button_renders_percentiles(monkeypatch):
    tips = TipFloor(p25=1e-6, p50=1e-6, p75=1.6e-6, p95=5e-4, p99=1.85e-3)
    monkeypatch.setattr(sizing_mod, "run_tips",
                        lambda on_done, on_error: on_done(tips))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _tips_button(view).on_click(None)
    text = " ".join(_texts(view))
    assert "0.0005" in text or "5.0e-04" in text.lower()
    assert "recommend" in text.lower()


def test_tips_failure_is_shown(monkeypatch):
    monkeypatch.setattr(sizing_mod, "run_tips",
                        lambda on_done, on_error: on_error(RuntimeError("down")))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _tips_button(view).on_click(None)
    assert any("tips unavailable" in t.lower() for t in _texts(view))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_sizing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arena.gui.views.sizing'`

- [ ] **Step 3: Write minimal implementation**

Create `arena/gui/sizing_worker.py`:

```python
"""Off-thread runners for the sizing calculator and the tip lookup. Same
contract as scan_worker.run_scan: callbacks fire FROM the worker thread."""

import asyncio
import threading
from typing import Callable

import httpx

from arena.flow.kelly import KellyInputs, KellyResult, solve_kelly
from arena.flow.tips import TipFloor, fetch_tips


def run_kelly(inputs: KellyInputs, on_done: Callable[[KellyResult], None],
              on_error: Callable[[Exception], None], solve_fn=None
              ) -> threading.Thread:
    fn = solve_fn or solve_kelly

    def worker() -> None:
        try:
            on_done(fn(inputs))
        except Exception as exc:
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


async def _tips_async() -> TipFloor:
    async with httpx.AsyncClient() as client:
        return await fetch_tips(client)


def run_tips(on_done: Callable[[TipFloor], None],
             on_error: Callable[[Exception], None], fetch_fn=None
             ) -> threading.Thread:
    fn = fetch_fn or (lambda: asyncio.run(_tips_async()))

    def worker() -> None:
        try:
            on_done(fn())
        except Exception as exc:
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
```

Create `arena/gui/views/sizing.py`:

```python
import flet as ft

from arena.flow.kelly import KellyInputs
from arena.flow.tips import recommend
from arena.gui import theme
from arena.gui.sizing_worker import run_kelly, run_tips

FIELDS = [
    ("hit_rate", "Hit rate (0-1)", "0.10"),
    ("winner_multiple", "Minimum winner multiple", "5.0"),
    ("tail_index", "Tail index alpha", "1.8"),
    ("max_drawdown", "Max drawdown (0-1)", "0.50"),
    ("ruin_tolerance", "Ruin tolerance (0-1)", "0.05"),
]


def build_sizing(page: ft.Page, on_back) -> ft.View:
    inputs = [ft.TextField(label=label, value=default, width=320)
              for _, label, default in FIELDS]
    compute_btn = ft.FilledButton("Compute size", bgcolor=theme.CYAN,
                                  color=theme.WHITE)
    tips_btn = ft.TextButton("Fetch live tips")
    out = ft.Column(spacing=theme.GAP, width=460)

    def error(message: str) -> None:
        out.controls.clear()
        out.controls.append(ft.Text(message, color=theme.VERDICT_COLORS["AVOID"]))
        page.update()

    def show_kelly(result) -> None:
        out.controls.clear()
        out.controls.append(ft.Text(
            f"Size: {result.f_constrained * 100:.1f}% of bankroll",
            size=20, weight=ft.FontWeight.W_500, color=theme.INK))
        out.controls.append(ft.Text(
            f"unconstrained Kelly {result.f_star * 100:.1f}%, "
            f"P(drawdown breach) {result.drawdown_prob * 100:.1f}%",
            size=12, color=theme.MUTED))
        for label, value in result.sensitivity:
            out.controls.append(ft.Text(f"{label}: {value * 100:.1f}%",
                                        size=13, color=theme.INK))
        out.controls.append(ft.Text(
            "Every input above is an assumption you supplied, not a measurement. "
            "The spread across those three rows is how much the answer depends "
            "on being right.", size=12, color=theme.MUTED))
        page.update()

    def show_tips(tips) -> None:
        out.controls.clear()
        out.controls.append(ft.Text("Jito landed tips (SOL)", size=16,
                                    weight=ft.FontWeight.W_500, color=theme.INK))
        out.controls.append(ft.Text(
            f"p50 {tips.p50:.6f}   p75 {tips.p75:.6f}   "
            f"p95 {tips.p95:.6f}   p99 {tips.p99:.6f}",
            size=13, color=theme.INK))
        out.controls.append(ft.Text(
            f"recommended: {recommend(tips, 'normal'):.6f} SOL — what is "
            "currently landing, not a guarantee of inclusion.",
            size=12, color=theme.MUTED))
        page.update()

    def do_compute(_) -> None:
        try:
            values = [float(f.value) for f in inputs]
        except (TypeError, ValueError):
            error("every field must be a number")
            return
        payload = KellyInputs(hit_rate=values[0], winner_multiple=values[1],
                              tail_index=values[2], max_drawdown=values[3],
                              ruin_tolerance=values[4])
        out.controls.clear()
        out.controls.append(ft.Text("simulating…", color=theme.MUTED))
        page.update()
        run_kelly(payload,
                  on_done=lambda r: page.run_thread(show_kelly, r),
                  on_error=lambda e: page.run_thread(
                      lambda exc=e: error(f"sizing failed: {exc}")))

    def do_tips(_) -> None:
        run_tips(on_done=lambda t: page.run_thread(show_tips, t),
                 on_error=lambda e: page.run_thread(
                     lambda: error("tips unavailable right now")))

    compute_btn.on_click = do_compute
    tips_btn.on_click = do_tips

    return ft.View(
        route="/sizing",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([
                ft.TextButton("Back", on_click=lambda _: on_back()),
                ft.Text("Sizing & tips", size=18, weight=ft.FontWeight.W_500,
                        color=theme.INK),
            ]),
            ft.Column(inputs + [ft.Row([compute_btn, tips_btn]), out],
                      spacing=theme.GAP,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ])
```

In `arena/gui/views/live.py`, change the signature and append the Sizing button **last** in the header so the sensitivity dropdown stays at index 3:

```python
def build_live(page: ft.Page, on_back, on_open_sizing) -> ft.View:
```

```python
            ft.Row([
                ft.TextButton("Back", on_click=lambda _: on_back()),
                ft.Text("Quant Microstructure Engine", size=18,
                        weight=ft.FontWeight.W_500, color=theme.INK),
                ft.Container(expand=True),
                sensitivity,
                ft.TextButton("Sizing", on_click=lambda _: on_open_sizing()),
            ]),
```

In `arena/gui/app.py`, add the import and route:

```python
from arena.gui.views.sizing import build_sizing
```

```python
    def show_live():
        page.views.clear()
        page.views.append(build_live(page, on_back=show_modes,
                                     on_open_sizing=show_sizing))
        page.update()

    def show_sizing():
        page.views.append(build_sizing(page, on_back=show_live))
        page.update()
```

In `tests/test_gui_live.py`, every `build_live(FakePage(), on_back=...)` call gains `on_open_sizing=lambda: None`, and add:

```python
def test_sizing_button_routes():
    clicked = {"flag": False}
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: clicked.__setitem__("flag", True))
    view.controls[0].controls[4].on_click(None)
    assert clicked["flag"] is True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_sizing.py tests/test_gui_live.py tests/test_gui_app.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add arena/gui/sizing_worker.py arena/gui/views/sizing.py arena/gui/views/live.py arena/gui/app.py tests/test_gui_sizing.py tests/test_gui_live.py
git commit -m "feat: sizing and Jito tip panel reachable from the QME"
```

---

## Verification checklist

After Task 15, confirm each of these by running the command and reading the output — not by assuming:

- [ ] `.venv/bin/pytest` — full suite green, no network used
- [ ] `.venv/bin/python -c "import arena.flow.signal, arena.stream.subscribe"` — engine imports without Flet
- [ ] `grep -rn "scipy\|numpy\|pandas" arena/` — no matches
- [ ] `grep -rn "sklearn" arena/ | grep -v train.py` — no runtime import outside the trainer
- [ ] `.venv/bin/python -m arena.gui` — splash → mode picker → both doors open
- [ ] In the QME, **Sizing** opens the calculator; Compute returns a fraction and **Fetch live tips** returns real percentiles
- [ ] `.venv/bin/python -m arena check <mint>` — the CLI still works unchanged
- [ ] Watch a real mint with a real key; confirm WARMUP → HEATING, then kill Wi-Fi and confirm the readout goes DISCONNECTED and shows no stale η
