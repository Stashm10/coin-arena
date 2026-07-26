# Coin Arena 

**Pre-buy rug checks for Solana meme coins.** Paste a token's mint address and
get a verdict in seconds — before you buy, not after.

-  **AVOID** — a mechanical rug setup was found
-  **CAUTION** — a couple of warning signs
-  **NO RED FLAGS** — nothing obvious found *(not the same as "safe" — read the caveats)*

It checks six things a candlestick chart can't show you: whether the dev can
still mint or freeze the token, how concentrated the supply is, whether the
launch was bundled by one person across many wallets, the dev wallet's launch
history, who funded the dev, and basic vitals (age, holders, liquidity).

---

## Download (Mac)

1. Go to the [**Releases**](https://github.com/Stashm10/coin-arena/releases) page and download `Coin Arena.zip`.
2. Double-click the zip to unzip it, then drag **Coin Arena** into your **Applications** folder.
3. **First launch:** right-click (or Control-click) the app → **Open** → **Open**.
   macOS shows a warning because the app isn't code-signed — this is expected,
   and you only have to do it once. After that it opens normally.

> The app is unsigned (code signing needs a paid Apple Developer account). If
> you'd rather not right-click-Open, that's the reason.

## How to use it

1. Open the app, paste a Solana **mint address** (copy it from DexScreener,
   Solscan, or your trading terminal), and click **Check**.
2. Read the verdict and the six checks below it.

**Optional but recommended — add a free API key.** Without one, the app runs in
"public mode" and only 3 of the 6 checks work. To unlock all six:

1. Get a free key at [helius.dev](https://helius.dev) (takes ~2 minutes, no card).
2. In the app, click **Settings**, paste the key, click **Save**.

Your key is stored only on your own machine and is never bundled or shared.

## Learning mode — teach it from your own results (optional)

Coin Arena can go beyond fixed rules and learn a **rug-probability** from your
own track record:

1. **Label outcomes.** Click **History** in the top bar to see your past scans.
   For each coin you know the fate of, tap **Rug**, **Clean**, or **Unsure**.
2. **Train the model** (from the source folder, occasionally — needs the `ml`
   extra):
   ```bash
   .venv/bin/pip install -e '.[ml]'
   .venv/bin/python -m arena.train
   ```
   It learns which warning signs actually predicted rugs *in your data* and
   prints the weights. It refuses to train on fewer than 20 labeled coins or a
   single class, so it never produces a garbage model.
3. **Scan.** After training, each scan shows a **"Model estimate: N% rug risk"**
   line alongside the rules verdict. The rules stay as the always-on baseline;
   the model is additive, and the sample count is always shown so you know how
   much to trust it.

Nothing runs in the background — labeling and training are both on-demand.

## The six checks

| Check | What it catches |
|---|---|
| **Authorities** | Dev can still mint infinite supply or freeze your wallet → **AVOID** |
| **Holder concentration** | A few wallets hold most of the supply |
| **Bundle detection** | Many wallets bought in the same block at launch (one person faking demand) |
| **Dev record** | The creator wallet has launched many tokens before (serial launcher) |
| **Funding trail** | The dev was funded by a wallet tied to coins that already rugged |
| **Vitals** | Age, holder count, liquidity (context only) |

---

##  Honest caveats — read this

-  **"NO RED FLAGS" does not mean "safe."** It means no *mechanical* rug setup
  was detected. The tool **cannot** detect intent, a Twitter/Telegram exit scam,
  paid influencers, or a slow bleed. Plenty of coins with no red flags still go
  to zero.
- This is **not financial advice.** Coin Arena never trades and never touches
  your wallet — it only reads public blockchain data. Every buy/sell decision
  is yours.
- Meme coins are extremely high risk. Only ever risk what you can afford to
  lose entirely.

---

## For developers

Coin Arena is a small Python app: a pure analysis engine (`arena/`) with a
Flet desktop GUI (`arena/gui/`) and a terminal CLI on top. The engine never
imports the GUI, so it's fully testable offline.

### Run from source

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[gui,dev]'
.venv/bin/python -m arena.gui          # desktop app
```

### Terminal CLI

```bash
.venv/bin/python -m arena set-key YOUR_HELIUS_KEY   # optional
.venv/bin/python -m arena check <mint address>      # scan a coin
.venv/bin/python -m arena verify                    # label past scans (24h+ old)
.venv/bin/python -m arena report                    # per-flag hit rates from YOUR data
```

Every scan is logged locally to SQLite. `verify` later checks what actually
happened to each coin, and `report` shows how well each red flag predicted
rugs *in your own data* — the foundation for tuning the checks with real
statistics instead of guesses.

### Build the Mac app

```bash
.venv/bin/flet pack arena/gui/__main__.py --name "Coin Arena" \
    --icon arena/gui/assets/app_icon.icns \
    --add-data "arena/gui/assets:arena/gui/assets"
```

Produces `dist/Coin Arena.app`. No API key is bundled — each user adds their own.

### Tests

```bash
.venv/bin/pytest             # offline, no network
.venv/bin/pytest -m live -v  # hits real APIs, needs a key
```

### Data sources

- **Helius** (free tier) — Solana RPC + enhanced transactions (5 of 6 checks)
- **DexScreener** (free, no key) — price and liquidity
- **Local SQLite** — accumulated wallet reputation for the funding-trail check
