# Coin Arena — Exit Measurement Harness (design)

Date: 2026-08-02
Status: approved for planning

## 1. Why this exists

The Quant Microstructure Engine shipped with zero validation. It fires EXIT
alerts from a Hawkes cascade-decay signal and a closed-form stopping rule, and
nobody — including its author — knows whether either beats a trailing stop.

Until that is measured, the engine's sensitivity thresholds are guesses and its
value is unknown. This harness answers one question:

> **Does selling on EXIT beat simpler mechanical rules?**

Secondary, from the same data: does the signal actually lead the price peak, and
by how much?

A negative result is a real result. The point is to find out, not to confirm.

## 1a. Phasing — only Phase 1 is being built now

The analysis is worthless until there are sessions to analyse, and there are
none. So the build is split, and **only Phase 1 is in scope for the current
implementation plan**:

| Phase | Scope | Status |
|---|---|---|
| **1 — Capture** | §5 tables (`watch_sessions`, `watch_signals`) and the engine writes that fill them | **Building now** |
| 2 — Resolution | §6 `replay.py` and the `watch_outcomes` table | Deferred |
| 3 — Analysis | §7 scoring and §8 report | Deferred |

The reasoning: data is perishable and analysis is not. Every watch that happens
before capture exists is a watch that can never be measured, whereas the scoring
code can be written any time the appetite arrives. Phase 1 is roughly a fifth of
the total work and adds no user-facing surface.

Phases 2 and 3 are specified below in full so the capture schema is designed
against its real consumer rather than guessed at. `watch_outcomes` is **not**
created in Phase 1 — `CREATE TABLE IF NOT EXISTS` runs on every `Store()`
construction, so adding it later costs nothing and creating it now would be an
unused table.

Revisit Phase 2 once roughly 30–40 sessions have accumulated.

## 2. Decisions already made

| Question | Decision |
|---|---|
| Primary question | Does EXIT beat simpler rules? |
| Capture scope | Every watch, automatically — no opt-in per coin |
| Baselines | Trailing stop (10/20/30%) and sell-at-peak (hindsight ceiling) |
| Horizon | 60 minutes from watch start |
| Entry convention | Price at the moment Watch was pressed |
| Resolution timing | On demand via CLI, never automatic |

**Entry convention rationale.** Because every watch is logged whether or not it
was traded, the user's real fill price is unknown. Scoring every rule from the
same watch-start price makes them directly comparable; a different real entry
shifts all rules equally and cannot change which one wins.

## 3. Constraints (inherited, still binding)

- **Free tier only.** No metered endpoints, no paid plans.
- **Nothing runs when the app is closed.** Resolution is a CLI command the user
  runs deliberately.
- **Advisory only** — no keys, no signing, no transactions.
- **No numpy, scipy, or pandas.** Python stdlib only.
- **Storage under 50 MB steady state.**
- `arena/research/` must import without Flet.

### One inherited constraint is deliberately changed

The QME design spec states: *"The engine never writes to SQLite."* This harness
requires that to change — a session that is never recorded cannot be measured.

The revised rule: **the engine writes only session metadata and state
transitions, never tape data.** The in-memory tape stays in memory and is still
discarded when a watch stops; what persists is one session row plus a handful of
transition rows, on the order of a kilobyte per watch. Writes happen on watch
start, on each state change, and on stop — not per trade — so the socket path
stays free of disk I/O.

This is a real relaxation of a stated constraint, recorded here rather than
quietly broken. The constraints it was protecting — bounded storage and nothing
running when the app is closed — both still hold.

## 4. Architecture

```
arena/
  research/                 pure functions, zero I/O
    rules.py                exit-rule simulators over a price path
    score.py                per-session scoring and aggregation
    report.py               rich-rendered comparison table
  replay.py                 network: rebuild a mint's price path from chain
  store.py                  + three tables (existing file)
  __main__.py               + `replay` and `report-exits` commands (existing)
```

`research/` takes lists of numbers and returns numbers. `replay.py` moves bytes.
This is the same split as `flow/` vs `stream/` and exists for the same reason:
every rule is testable offline against hand-built paths.

## 5. Data captured

Three new tables in the existing SQLite database.

**`watch_sessions`** — one row per Watch press:

```sql
CREATE TABLE IF NOT EXISTS watch_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    started_ts INTEGER NOT NULL,
    entry_price REAL,
    sensitivity TEXT NOT NULL,
    hazard_pct REAL NOT NULL,
    toggles TEXT NOT NULL,
    resolved_ts INTEGER
);
```

`toggles` is a JSON list of the hazard multipliers active at start, so a session
scored later can be interpreted against what the user actually believed.

`entry_price` is **the price of the first decoded trade after Watch was
pressed**, not a price fetched at press time — at press time no trade has
arrived and no price exists. It is nullable for a session that never saw a
decodable trade; such sessions are skipped at scoring with a stated reason,
never silently dropped.

**`watch_signals`** — every state transition during the session:

```sql
CREATE TABLE IF NOT EXISTS watch_signals (
    session_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    eta REAL, lam REAL, hold_drift REAL
);
```

Transitions only, not every tick — the engine emits a state once per second and
storing all of them would be 3,600 rows per session for no analytical gain.
This table answers questions the headline number cannot, such as how often
COOLING reverts to HEATING rather than progressing to EXIT.

**`watch_outcomes`** — filled in by replay:

```sql
CREATE TABLE IF NOT EXISTS watch_outcomes (
    session_id INTEGER PRIMARY KEY,
    peak_price REAL NOT NULL,
    peak_ts INTEGER NOT NULL,
    bars_json TEXT NOT NULL,
    resolved_ts INTEGER NOT NULL
);
```

**`bars_json` holds one-second bars, not raw trades.** A busy coin does
thousands of trades an hour; one-second bars cap at 3,600 points over the
horizon, which is ample resolution for simulating a trailing stop. Roughly
100 KB per session, so 100 sessions lands near 10 MB — inside budget, and it
means new exit rules can be tested later without re-fetching anything.

## 6. Resolution (`python -m arena replay`)

Walks sessions where `resolved_ts IS NULL` and `started_ts` is older than the
60-minute horizon. For each:

1. Page that mint's transaction history via `RpcClient.enhanced_txs`.
2. Decode each transaction with the existing `arena/stream/decode.py` —
   the same decoder verified against 926 live pump.fun trades.
3. Reconstruct price from the bonding-curve reserves carried in each trade.
4. Bucket into one-second bars over `[started_ts, started_ts + 3600]`.
5. Record the peak and its timestamp; write `watch_outcomes`.

Cost is roughly 20–50 API calls per session. Sessions that cannot be resolved
(no transactions returned, mint migrated to a venue the decoder does not read,
RPC failure) are left unresolved with the reason logged, and `replay` continues
to the next one. A partial failure never aborts the run.

Post-graduation trades on Raydium/PumpSwap are **not** decoded — the price path
ends where the bonding curve does. Sessions that graduated within the horizon
are flagged and excluded from scoring rather than scored on a truncated path.

## 7. Scoring (`arena/research/`)

Every rule is a pure function over `bars: list[tuple[int, float]]` returning the
price it would have sold at, or `None` if it never triggered:

- `exit_on_signal(bars, signal_ts) -> float | None`
- `trailing_stop(bars, pct) -> float | None`
- `peak(bars) -> float`

Per session, each rule yields:

- **multiple** — exit price / entry price
- **capture ratio** — (exit price − entry) / (peak − entry), the fraction of the
  available move actually taken

Capture ratio is the primary metric because it isolates exit quality from
whether the coin happened to pump at all.

Aggregated across sessions: median and mean multiple, win rate (fraction with
multiple > 1), and median capture ratio.

## 8. The report (`python -m arena report-exits`)

Rendered with `rich`, already a dependency. Three blocks:

**Headline table** — one row per rule (EXIT, trailing 10/20/30%, peak), columns
for median multiple, mean multiple, win rate, median capture ratio.

**Split by reason** — `cascade decay` and `hazard exceeds drift` scored
separately. They are different signals and one may work while the other is
noise; averaging them would hide that.

**Timing distribution** — seconds between the EXIT signal and the peak, median
and interquartile range. A negative median means the signal lags the peak and
the core premise is wrong. This is the single most falsifying number the harness
produces.

**Sample-size honesty.** Below 20 resolved sessions every number is bannered as
not meaningful, matching the discipline `train.py` already applies by refusing
to fit under 20 labels. Twenty is a floor, not a sufficiency threshold — on
heavy-tailed data, medians stay unstable well past it, and the report says so.

## 9. Failure modes

- **Unresolvable session** — logged with a reason, left unresolved, skipped by
  the report's denominator. Never silently counted as a zero.
- **Rule never triggers** (a coin that only ever rises within the horizon) —
  reported as "never triggered" with a count, not folded into the median as if
  it had sold at the last bar.
- **Missing entry price** — session excluded from scoring with a stated reason.
- **Graduated mid-horizon** — flagged and excluded, since the path is truncated.

## 10. Testing

All rules are pure functions over short hand-built paths where the correct
answer is computable on paper:

- Clean rise-then-fall: the 20% trailing stop must exit at a specific named bar.
- Monotone rise: every rule hits the ceiling; trailing stops never trigger.
- Gap down between bars: the stop fills at the gapped price, not the threshold.
- Flat path: capture ratio is undefined (peak equals entry) and must not divide
  by zero.
- A session where no rule triggers, asserted to be reported as such.

Bar bucketing and peak detection are tested against synthetic trade lists.
`replay.py`'s paging is tested with the existing `make_client` mock transport.
No test touches the network.

## 11. Out of scope for v1

- Slippage, fees, and priority-fee modelling. Every rule is scored on the mid
  price from reserves; real fills would be worse, and worse by different amounts
  per rule. This is a stated limitation, not an oversight.
- Tuning the sensitivity thresholds from the results. Measure first; changing the
  thresholds and the measurement together would make both uninterpretable.
- Post-graduation price paths.
- Any GUI surface. This is offline research run from the CLI.

## 12. What a good outcome looks like

Not "EXIT wins." A defensible answer either way:

- If EXIT's median capture ratio beats every trailing stop, the engine earns its
  complexity.
- If it does not, that is publishable in the README and a stronger portfolio
  result than an unvalidated build — it demonstrates the ability to kill one's
  own idea with evidence.

The failure mode to avoid is a number too small or too noisy to support either
conclusion, which is why sample size is bannered rather than buried.
