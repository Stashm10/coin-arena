# Coin Arena 

**Two tools for Solana meme coins.** On launch, pick one:

- **Rug Pull Checker** — paste a mint address, get six checks and a verdict
  before you buy.
- **Quant Microstructure Engine** — paste a mint you already hold and get a
  live exit signal computed from the coin's own trade stream.

The first tells you what to avoid. The second tells you when the move is over.

---

## Download (Mac)

1. Go to the [**Releases**](https://github.com/Stashm10/coin-arena/releases) page and download `Coin Arena.zip`.
2. Double-click the zip to unzip it, then drag **Coin Arena** into your **Applications** folder.
3. **First launch:** right-click (or Control-click) the app → **Open** → **Open**.
   macOS shows a warning because the app isn't code-signed — this is expected,
   and you only have to do it once. After that it opens normally.

> Apple Silicon only. The app is unsigned (code signing needs a paid Apple
> Developer account), which is why the right-click-Open step exists.

**Add a free API key.** Without one, the Rug Pull Checker runs in "public mode"
with only 3 of 6 checks, and the Quant Microstructure Engine won't run at all.

1. Get a free key at [helius.dev](https://helius.dev) (takes ~2 minutes, no card).
2. In the app: **Settings** → paste → **Save**.

Your key is stored only on your own machine and is never bundled or shared.

---

## Rug Pull Checker

Paste a mint address, click **Check**, get a verdict in a few seconds:

-  **AVOID** — a mechanical rug setup was found
-  **CAUTION** — a couple of warning signs
-  **NO RED FLAGS** — nothing obvious found *(not the same as "safe" — read the caveats)*

### The six checks

| Check | What it catches |
|---|---|
| **Authorities** | Dev can still mint infinite supply or freeze your wallet → **AVOID** |
| **Holder concentration** | A few wallets hold most of the supply |
| **Bundle detection** | Many wallets bought in the same block at launch (one person faking demand) |
| **Dev record** | The creator wallet has launched many tokens before (serial launcher) |
| **Funding trail** | The dev was funded by a wallet tied to coins that already rugged |
| **Vitals** | Age, holder count, liquidity (context only) |

### Trace funding graph (optional)

A button on the scan result. It walks each launch buyer's funding back two hops
and reports the Shannon entropy of the sources:

> *"12 of 15 launch buyers trace back to one wallet — H̃ = 0.21"*

That's one person in fifteen costumes. Low entropy means concentrated funding;
high entropy means genuinely independent buyers. Crucially, the walk stops at
exchange addresses and treats each as its own source — twenty people who each
withdrew from Coinbase share a *venue*, not a *source*, and won't be flagged.

It runs only when you click it, because it costs about 40 API calls.

### Learning mode (optional)

Coin Arena can learn a rug-probability from your own track record:

1. **Label outcomes.** **History** → tap **Rug**, **Clean**, or **Unsure** on past scans.
2. **Train** (occasionally, from source — needs the `ml` extra):
   ```bash
   .venv/bin/pip install -e '.[ml]'
   .venv/bin/python -m arena.train
   ```
3. **Scan.** Each result then shows a **"Model estimate: N% rug risk"** line next
   to the rules verdict, always with the sample count so you know how much to
   trust it.

It refuses to train on fewer than 20 labeled coins or a single class, so it
never produces a garbage model. Nothing runs in the background.

---

## Quant Microstructure Engine

Paste a mint you hold and press **Watch**. Coin Arena opens a live stream of
that coin's trades and fits a **Hawkes process** to them — the model used for
earthquake aftershocks and order-flow bursts, where each event raises the
chance of the next. Then you go back to your trading terminal; the app reaches
you by sound and notification.

### What the states mean

| State | Meaning |
|---|---|
| **WARMUP** *(grey)* | Collecting. Needs 40 trades before the cascade math is meaningful; the counter shows progress. |
| **HEATING** *(green)* | Each buy is still triggering more buys. The move is feeding itself. |
| **COOLING** *(amber)* | Momentum fading, but not long enough to call it. A warning, not a verdict — it often returns to HEATING. |
| **EXIT** *(red)* | Fires the alert. Latches — it won't flip back. |
| **DISCONNECTED** *(red)* | The stream dropped. **No trades showing does NOT mean the coin is quiet.** |

That last one is deliberate. A dead connection and a dead coin both look like
silence, so when the feed drops the app blanks every number rather than leaving
stale ones that would read as calm.

### The two EXIT signals

You get one chime and one notification titled **EXIT**, telling you which fired:

1. **"cascade decay"** — the branching ratio η and the trade intensity λ have
   both fallen well off their session peaks and stayed there. Nobody's rugging;
   the crowd just left.
2. **"hazard exceeds drift"** — the coin's estimated log-drift no longer
   compensates for the assumed risk of a sudden total loss.

The readout underneath shows the working:

```
η = 0.62 (peak 0.85)   λ = 4.3/s (peak 12.1/s)
hold drift = -0.45/hr  assumed crash hazard 90%/hr (mint authority live ×2.5)
```

Peaks matter more than absolute values — falling away from *your own high* is
the signal, not any fixed threshold.

### The controls

**Sensitivity** (Early / Balanced / Late) sets how much decay is required, and
for how long, before the alert fires.

**Three hazard toggles** — mint authority still live, supply concentrated,
creator wallet selling — scale the assumed crash risk (×2.5, ×1.8, ×4.0) on a
20%/hr base. They take effect on a running watch.

**Sizing** opens a position-size calculator and a live
[Jito](https://jito.wtf) landed-tip lookup. The number worth reading isn't the
recommended size — it's the row showing what that size becomes if your hit rate
is *half* what you assumed. On these return distributions that gap is brutal,
and seeing it is the point.

### The assumed crash hazard is an assumption

Coin Arena cannot measure how likely a rug is. You tell it what you believe,
and it does exact arithmetic on your belief. Set it wrong and it will
confidently tell you the wrong thing. The word "assumed" appears everywhere it
does, for that reason.

### Session capture

Every watch is recorded locally — settings, entry price, and each state
transition — so the signal can be scored later against what the coin actually
did. About a kilobyte per watch, written on transitions rather than per trade.
Nothing leaves your machine.

---

##  Honest caveats — read this

-  **"NO RED FLAGS" does not mean "safe."** It means no *mechanical* rug setup
  was detected. The tool **cannot** detect intent, a Twitter/Telegram exit scam,
  paid influencers, or a slow bleed. Plenty of coins with no red flags still go
  to zero.
- **HEATING is not a buy signal.** It's the absence of an exit signal. It is
  exactly as consistent with "this has 10x left" as with "you're two minutes
  from the top." The engine has no notion of where you are in a move.
- **EXIT does not mean the coin is going to zero.** It means the buying stopped
  feeding itself. Coins flatten, chop, and sometimes run again.
- **The exit signal is unvalidated.** Nobody has yet measured whether it beats a
  trailing stop, and the sensitivity thresholds are chosen, not fitted. Session
  capture exists precisely so that question can be answered with data instead of
  opinion. Treat the output accordingly.
- **This is not financial advice.** Coin Arena never trades and never touches
  your wallet — it only reads public blockchain data. Every buy and sell
  decision is yours.
- Meme coins are extremely high risk. Only ever risk what you can afford to
  lose entirely.

---

## For developers

A small Python app: a pure analysis engine (`arena/`), a Flet desktop GUI
(`arena/gui/`), and a terminal CLI. The engine never imports the GUI, so it's
fully testable offline — 312 tests, none of which touch the network.

```
arena/
  checks/      the six rug checks, plus funding entropy
  flow/        pure math — Hawkes fit, optimal stopping, Kelly, tips
  stream/      network — Helius WebSocket, trade decoding, tape buffer
  gui/         Flet views and worker threads
```

`flow/` takes lists of numbers and returns numbers. `stream/` moves bytes and
does no arithmetic. That split is what makes the models testable against
synthetic data with no API key.

### Run from source

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[gui,dev]'
.venv/bin/python -m arena.gui
```

### Terminal CLI

```bash
.venv/bin/python -m arena set-key YOUR_HELIUS_KEY   # optional
.venv/bin/python -m arena check <mint address>      # scan a coin
.venv/bin/python -m arena verify                    # label past scans (24h+ old)
.venv/bin/python -m arena report                    # per-flag hit rates from YOUR data
```

### Build the Mac app

```bash
SSL_CERT_FILE=$(.venv/bin/python -c "import certifi; print(certifi.where())") \
  .venv/bin/flet pack arena/gui/__main__.py --name "Coin Arena" \
  --icon arena/gui/assets/app_icon.icns \
  --add-data "arena/gui/assets:arena/gui/assets"
```

Produces `dist/Coin Arena.app`. The `SSL_CERT_FILE` prefix is required —
python.org Python builds ship no CA certificates, so `flet pack` can't download
its client binary without it. No API key is bundled; each user adds their own.

### Tests

```bash
.venv/bin/pytest             # offline, no network, no key
.venv/bin/pytest -m live -v  # hits real APIs, needs a key
```

### Data sources

- **Helius** (free tier) — Solana RPC, enhanced transactions, and the
  `logsSubscribe` WebSocket that feeds the exit engine
- **DexScreener** (free, no key) — price and liquidity
- **Jito** (free, no key) — landed-tip percentiles
- **Local SQLite** — scan history, wallet reputation, funding-edge cache, and
  watch sessions

### Design notes

Specs and implementation plans live in `docs/superpowers/`. Two corrections
worth knowing if you read the code:

- **"Sell when η crosses 1" is wrong.** A fitted branching ratio is almost
  always below 1, because η ≥ 1 describes a process that explodes to unbounded
  intensity. The usable signal is η's trajectory against its own peak.
- **No HJB solver is needed.** For log utility with a total-loss Poisson jump,
  the optimal-stopping boundary is closed-form: sell when
  `log_drift_per_s − λ_c < 0`.
