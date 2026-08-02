# Coin Arena — Quant Microstructure Engine (design)

Date: 2026-08-01
Status: approved for planning

## 1. What this adds

Coin Arena today answers one question — *is this a rug?* — from hand-picked
thresholds, with an optional logistic model trained on manually labeled scans.

This design adds a second, independent capability: a **Quant Microstructure
Engine (QME)** that answers *when do I get out?* from live order flow, using
first-principles math rather than fitted patterns. The existing rug checker,
its history, its labeling, and its model stay exactly as they are.

On launch the app presents two doors:

- **Rug Pull Checker** — the current six checks, verdict, History, labeling,
  model line. One upgrade: an opt-in funding-entropy trace.
- **Quant Microstructure Engine** — paste a mint you hold, watch a live exit
  signal derived from a Hawkes process fit and a crash-hazard stopping rule.

### Constraints (set by the user, non-negotiable)

- **Free.** No paid API tiers, no metered endpoints, no funded wallets.
- **Never runs when closed.** No daemon, no background process, no launch
  agent. Sockets open on Watch, close on stop or window close.
- **Advisory only.** The app never holds a private key, never signs, never
  submits a transaction. Every output is a number for the user to act on
  manually in Axiom.

## 2. Decisions already made

| Question | Decision |
|---|---|
| Execution | Advisory only; user trades in Axiom |
| Priority | Exit timing first |
| Position input | User pastes the mint after buying |
| v1 scope | Exit engine + funding-entropy upgrade |
| Existing logistic model | Kept unchanged |
| Alerting | Sound alert **and** macOS notification |
| Sensitivity | One Early / Balanced / Late slider |

## 3. Data sources and why

| Source | Use | Cost |
|---|---|---|
| Helius WebSocket `logsSubscribe` | Per-trade event stream for watched mints | Free key; 20 credits/MB streamed against a 1M/month budget |
| Helius enhanced transactions | Funding-graph hops | Free key; 10 req/s |
| `bundles.jito.wtf/api/v1/bundles/tip_floor` | Landed-tip percentiles | Free, no key |
| DexScreener | Unchanged (rug checker vitals) | Free, no key |

**PumpPortal is rejected.** `subscribeNewToken` and `subscribeMigration` are
free, but the stream we would need — `subscribeTokenTrade` — is metered at
0.01 SOL per 10,000 events and requires an API key plus a wallet funded with
at least 0.02 SOL. That violates the free constraint.

**Credit budget.** A heavy session watching three coins for two hours streams
on the order of tens of megabytes, i.e. low hundreds of credits against
1,000,000/month. Streaming is not the binding cost; the funding-graph trace is,
which is why it is opt-in (§6).

## 4. Architecture

```
arena/
  flow/                  pure math, zero network, zero I/O
    hawkes.py            exponential-kernel Hawkes MLE
    hazard.py            drift-vs-hazard optimal stopping rule
    signal.py            state machine combining both signals
    kelly.py             ruin-constrained position sizing
    tips.py              Jito tip percentile advisor
  stream/                network only, zero math
    subscribe.py         Helius logsSubscribe client, reconnect, heartbeat
    decode.py            pump.fun TradeEvent Borsh decode
    tape.py              bounded per-mint ring buffer
  checks/
    entropy.py           H(F) over launch-buyer funding sources
  gui/views/
    mode_picker.py       two-door launch screen
    live.py              QME screen
```

`flow/` takes lists of timestamps and prices and returns numbers. `stream/`
moves bytes and does no arithmetic. This split is what makes the whole engine
testable offline with synthetic data and no API key.

Neither door imports the other. Shared: `rpc.py`, `store.py`, `settings.py`,
`gui/theme.py`.

**Dependencies: none added.** All math is pure-Python stdlib. `scikit-learn`
stays confined to the optional `ml` extra used by the offline trainer, so the
packaged `.app` does not grow.

## 5. Module: exit engine

### 5.1 The tape

`logsSubscribe` with `mentions: [mint]` yields one notification per transaction
touching the mint. Each notification produces a tape event:

- **Arrival timestamp**, stamped locally on receipt.
- **Decoded `TradeEvent`** where available: pump.fun emits a fixed Borsh layout
  in `Program data:` containing `isBuy`, SOL amount, token amount, and both
  virtual reserves. Reserves yield an exact price, so the tape is a price path,
  not merely an arrival process.
- **Fallback** for non-pump programs (post-graduation Raydium/PumpSwap):
  direction parsed from log strings; price unavailable, which degrades signal 2
  to unavailable while signal 1 continues to work.

**Timestamp honesty.** Local arrival time includes network jitter of roughly
50–200 ms. The engine operates on decay constants measured in seconds; it does
not claim, and must not display, millisecond precision.

Storage: a ring buffer of 2,000 events per mint (~200 KB). Nothing is written
to SQLite by the QME.

### 5.2 Hawkes fit

Exponential kernel, conditional intensity:

```
λ(t) = μ + Σ_{t_i < t} α · exp(−β(t − t_i))
```

Exact log-likelihood via the standard O(n) recursion:

```
ℓ = Σ_i log(μ + α·A_i) − μT − (α/β)·Σ_i (1 − exp(−β(T − t_i)))
A_i = exp(−β(t_i − t_{i−1})) · (1 + A_{i−1}),   A_0 = 0
```

Fit (μ, α, β) by Nelder–Mead in log-space (parameters constrained positive by
construction) over a rolling window: the last 300 events or 120 seconds,
whichever is smaller. Refit once per second, not per event. Cost is roughly 50
likelihood evaluations over 300 events — sub-millisecond in pure Python.

Branching ratio η = α/β.

**Why not "η crosses 1".** In a fitted Hawkes process η < 1 almost always
holds, because η ≥ 1 describes a process that explodes to unbounded intensity.
An estimator drifting from 0.6 to 0.5 is the normal state of every coin, alive
or dying. A trigger on η < 1 would essentially never fire. The usable signal is
the trajectory, not the unit crossing.

### 5.3 Signal 1 — cascade decay

Track η against its running peak η_peak and λ(t) against λ_peak, both over the
current watch session.

Fire when, sustained for P seconds:

```
η < c₁ · η_peak   AND   λ(t) < c₂ · λ_peak
```

Sensitivity slider sets (c₁, c₂, P):

| Setting | c₁ | c₂ | P |
|---|---|---|---|
| Early | 0.70 | 0.50 | 3 s |
| Balanced | 0.55 | 0.40 | 6 s |
| Late | 0.45 | 0.30 | 10 s |

Default is **Balanced**. These starting values are explicitly provisional and
expected to move once observed against live tape.

Warm-up: no signal output until at least 40 events are in the window.

### 5.4 Signal 2 — optimal stopping

Price follows a jump-diffusion with a Poisson total-loss component:

```
dS_t = μ S_t dt + σ S_t dW_t − S_{t⁻} dN_t,   N_t ~ Poisson(λ_c)
```

For log utility with a total-loss jump, the optimal-stopping boundary is
closed-form — no PDE solver is required. The drift of log-wealth from
continuing to hold is:

```
μ̂ − σ̂²/2 − λ_c
```

Sell when it turns negative.

- **μ̂, σ̂** are estimated from the live price path implied by decoded reserves.
- **λ_c is an assumption, not an estimate.** It is a user-set base hazard,
  scaled by structural facts the rug checker already extracts (mint authority
  still live, top-10 concentration), and jumped hard on observable events
  (creator wallet selling, liquidity removed).

**This seam is displayed, not hidden.** The UI shows "assumed crash hazard:
N%/hr" alongside the multipliers that produced it. The arithmetic above it is
exact; the input is a belief, and it is labeled as one.

If price is unavailable (non-pump fallback), signal 2 reports UNAVAILABLE
rather than guessing.

### 5.5 State machine

States: `WARMUP → LIVE → {HEATING, COOLING, EXIT}`, plus `DISCONNECTED`.

EXIT fires on either signal and reports which one fired. On firing: sound alert
and macOS notification, both, every time.

## 6. Module: funding entropy

Upgrades the rug checker. Reuses the launch-buyer set `bundles.py` already
collects; does not re-fetch it.

For each launch buyer, walk backward to the SOL transfer that funded it before
it bought, then that funder's funder, to k = 2 hops. Each wallet resolves to a
root source. With p_i the share of launch buyers rooted at source i:

```
H(F) = −Σ p_i ln(p_i)
H̃ = H / ln(N)   ∈ [0, 1]
```

Displayed as both the normalized figure and plain language: *"12 of 15 launch
buyers trace back to one wallet — H̃ = 0.21"*.

### 6.1 Root-node termination (correctness-critical)

A naive walk collapses every Coinbase-funded wallet into a single root, craters
entropy, and reports "cabal" on a launch of genuinely independent buyers. The
walk therefore terminates at **root-like** nodes, each counted as its own
distinct source:

- known CEX hot wallets, from a small bundled address list;
- any wallet whose transaction count exceeds a high threshold (a relay wallet
  has tens of transactions; an exchange hot wallet has millions);
- k = 2 hops reached.

This distinction separates a real signal from a false-alarm generator and gets
dedicated tests.

### 6.2 Cost and caching

20 buyers × 2 hops is up to 40 enhanced-transaction calls — several seconds at
10 req/s and a visible share of the credit budget if run on every scan. It
therefore does **not** run automatically. The scan result gets a **Trace
funding graph** button.

Resolved wallet→funder edges cache to a new SQLite table
(`funding_edges(child, parent, resolved_ts, is_root)`), so overlapping traces
are nearly free. Expected size well under 1 MB.

### 6.3 Honest limit

Entropy is a measurement, but converting it into AVOID still requires a chosen
cut. This replaces a guessed threshold on a crude quantity with a guessed
threshold on a rigorous one, and shows the user the underlying number and tree.
That is the gain — not the elimination of judgment.

## 7. Module: sizing and tips

**`flow/kelly.py`.** Inputs are stated beliefs: bankroll, hit rate p, minimum
winner multiple (the Pareto scale x_m — the smallest payoff that counts as a
win), tail index α, maximum acceptable drawdown γ, ruin tolerance δ.
Monte-Carlos a mixture — total loss with probability 1−p, Pareto(α, x_m) payoff
otherwise — maximizes E[ln(1 + f·X)] over a grid of f, then reduces f until
P(drawdown > γ) ≤ δ across simulated trade sequences. Seeded for determinism.

The primary output is not f* alone but the sensitivity table beside it: what f*
becomes when the hit rate is half what was assumed. On heavy tails that gap is
large, and displaying it is the purpose of the module.

**`flow/tips.py`.** Fetches Jito landed-tip percentiles on demand, displays the
distribution, recommends a percentile. Scope is bounded honestly: the user is
typing a number into Axiom, whose own fee logic sits between the user and the
block. The module reports what is currently landing; it does not promise
inclusion.

## 8. Failure modes

**Silent socket death is the dangerous one.** For this engine, absence of
trades *is* the signal, so a dead socket is indistinguishable from a coin going
quiet — the tool would sit calmly implying "nothing is happening" while blind.
Treatment:

- heartbeat against the socket;
- a hard `DISCONNECTED` state that suppresses all signal output rather than
  displaying stale η;
- reconnect with exponential backoff, refusing to resume fitting until the
  window refills.

Silence must never be presented as calm.

Ordinary failures: absent Helius key disables the QME with a pointer to
Settings; rate limiting and credit exhaustion surface as banners; malformed or
undecodable log payloads are skipped with a counter, never crashing the tape.

## 9. Resources

- Ring buffer: ~200 KB per watched mint; three concurrent watches under 1 MB.
- CPU: one Nelder–Mead refit per second per watched mint, sub-millisecond each.
- Sockets close on stop or window close. No persistence, no background work.

Flet's own footprint dominates total memory; the engine's contribution is
negligible against the 50 MB target.

## 10. Testing

All math is pure functions over plain data, so the suite runs offline with no
network, no key, and no mocking framework.

- **Hawkes fitter:** simulate a process with known (μ, α, β) by Ogata thinning;
  assert recovery within tolerance.
- **Borsh decode:** golden vectors from real `TradeEvent` payloads.
- **Entropy:** hand-built funding graphs, including the CEX-collapse trap and
  the high-transaction-count root rule.
- **State machine:** scripted event sequences — dying cascade, false lull,
  mid-session disconnect — asserting exact state transitions.
- **Kelly:** seeded runs asserting monotonicity in p and α, and that the
  drawdown constraint binds where expected.
- **Stream client:** reconnect and heartbeat behavior against a fake socket.

## 11. Explicitly out of scope for v1

- Trade execution, key handling, transaction signing.
- A full HJB PDE solver (§5.4 shows the closed form makes it unnecessary here).
- Scoring the pump.fun firehose at t=0; the free credit budget does not
  support graph tracing at launch rates.
- Wallet-address position auto-detection.
- Replacing or removing the existing rug checker, its history, its labeling, or
  its logistic model.

## 12. What this will and will not do

It will give a defensible, real-time, first-principles read on whether a buying
cascade is still self-sustaining, and exact arithmetic for a stopping decision
given stated beliefs about crash risk.

It will not predict which coin pumps. The stopping rule's key input (λ_c) is an
assumption; the Hawkes signal describes flow that has already happened; and
network jitter bounds timing resolution at roughly a tenth of a second. The
edge, if any, is in exiting a fading cascade before the price chart shows it —
not in foresight.
