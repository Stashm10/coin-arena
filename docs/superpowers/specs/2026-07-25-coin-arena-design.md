# Coin Arena — Design Spec

**Date:** 2026-07-25
**Status:** Approved in brainstorm; pending user review of this document

## Purpose

A downloadable Mac desktop app ("Coin Arena") for memecoin traders: paste a
Solana mint address seconds-to-minutes after launch, get a fast (~5–10s)
pre-buy rug verdict with evidence. Every scan is logged locally; outcomes are
verified later so the user accumulates a personal dataset of which red flags
actually predicted rugs — the foundation for fitting a real statistical model
once a few hundred labeled scans exist.

**Explicitly out of scope (v1):** pump/upside prediction (not credibly
possible from on-chain data alone — deliberately excluded, not deferred);
full per-wallet PnL computation (v2); Windows/Linux builds (structured for,
not shipped); auto-trading of any kind (never — the app is analysis only);
server components (everything runs on the user's machine).

## Key decisions (made with user)

| Decision | Choice |
|---|---|
| Primary job | Pre-buy rug filter, not pump predictor |
| Speed budget | ~5–10s per scan with Helius key; ~15s degraded on public RPC |
| Learning loop | Yes: log scans, verify outcomes later, report per-flag hit rates |
| Interface | Desktop GUI app (Flet), distributable as a Mac .app; debug CLI included |
| Name / brand | "Coin Arena"; Circuit Knight logo (original line-art knight with PCB node pads); white + cyan theme (#0891B2 primary), color reserved for verdicts; flat, no flashy effects |
| Data access | First-launch setup: paste free Helius key (helius.dev link) OR Skip → public RPC mode with degraded checks, clearly labeled |
| Platforms | Mac first; repo structured so Windows via GitHub Actions is config, not rewrite |
| Verdict style | Categorical (AVOID / CAUTION / NO RED FLAGS) — no invented percentages until the user's own data can calibrate real ones |
| Project home | New repo `~/coin_arena`, separate from the whale tracker |

## Architecture

Two layers, hard boundary: the GUI never touches the network or database.

```
GUI (Flet: splash / check / history / settings)
        │  engine.check(mint) → ScanResult
        ▼
Engine (pure Python library)
  rpc client (Helius key mode | public fallback mode)
  six checks (parallel, asyncio)
  scoring → verdict
  store (SQLite: scans, wallets, outcomes)
  verify (label old scans via DexScreener)
  report (per-flag hit rates)
```

A debug CLI (`python -m arena check|verify|report`) wraps the same engine.

## The six checks

Each returns `Finding(check, severity, evidence)` where severity ∈
{DISQUALIFIER, WARNING, PASS, INFO}. All run concurrently; per-check timeout
8s — a timed-out check reports `INFO "check unavailable"` and never blocks
the verdict.

1. **Authorities** (`getAccountInfo` on mint, jsonParsed). Mint authority not
   revoked → DISQUALIFIER ("dev can print supply"). Freeze authority not
   revoked → DISQUALIFIER ("dev can block selling"). Works in public mode.
2. **Holder concentration** (`getTokenLargestAccounts` + `getTokenSupply`,
   owner resolution and pool/bonding-curve exclusion reusing the
   system-program-owner technique from the whale tracker). Top-10 human
   share >55% → DISQUALIFIER; >35% → WARNING. Any single human wallet >15%
   → WARNING. Works in public mode.
3. **Bundle detection** (earliest transactions of the mint via Helius
   Enhanced Transactions API, paginate to the coin's first ~60s of life;
   group buyer wallets by slot). ≥8 distinct buyers in one slot →
   DISQUALIFIER; ≥4 → WARNING. Public mode: degraded to INFO "needs Helius
   key" (enhanced parsing unavailable).
4. **Dev record** (creator wallet = fee payer of the mint's creation tx;
   count its prior token creations via its enhanced tx history, sample most
   recent 100 txs). ≥8 prior launches → DISQUALIFIER; ≥3 → WARNING. Evidence
   lists prior mints found. Public mode: INFO "needs Helius key".
5. **Funding trail** (first incoming SOL transfer to the creator wallet =
   funder). If funder is already linked in the local DB to ≥1 previously
   scanned coin labeled RUGGED → DISQUALIFIER ("funded by known rugger's
   wallet"). Funder always recorded, so this check strengthens with every
   scan+verify cycle. Public mode: INFO "needs Helius key".
6. **Vitals** (holder count via Helius DAS `getTokenAccounts`, one page of
   1000 — reported exactly below 1000, else "1000+"; coin age from first
   tx; DexScreener pair liquidity if graduated; public mode shows age and
   liquidity only). Always INFO — context, never verdict input. Includes
   **smart-money lite**: "N of the top 20 holders previously appeared in
   coins that survived" from the local wallets table.

## Verdict

- Any DISQUALIFIER → 🔴 **AVOID** (list all).
- Else ≥2 WARNINGs → 🟡 **CAUTION**.
- Else → 🟢 **NO RED FLAGS**, always captioned *"no red flags ≠ safe"*.

All thresholds live in one `thresholds.py` constants module — the future
model-fitting step replaces this module's logic, nothing else.

## Data model (SQLite, `~/Library/Application Support/CoinArena/arena.db`)

- `scans(id, ts, mint, symbol, verdict, price_usd_at_scan, scan_json)` —
  price_usd_at_scan from DexScreener (nullable, pre-graduation coins have
  none); scan_json holds every finding with raw evidence (the future
  feature matrix).
- `coin_outcomes(mint PRIMARY KEY, scanned_ts, verified_ts, outcome)` —
  outcome ∈ RUGGED, DEAD, ALIVE, UNKNOWN.
- `wallets(address PRIMARY KEY, role, times_seen, times_in_rugged,
  times_in_survivors)` — roles: creator, funder, top_holder. Feeds funding
  trail + smart-money lite.

## Verify & report (the learning loop)

- `verify`: for each scan ≥24h old without an outcome, query DexScreener:
  no pair or liquidity <$1,000 → DEAD; price ≤10% of price-at-scan (when
  price-at-scan was recorded) → RUGGED; otherwise ALIVE. Updates
  `coin_outcomes` and increments wallet counters. Runs on demand: GUI runs
  it automatically at app launch (a few seconds, spinner on splash), CLI via
  `python -m arena verify`. No background process — consistent with the
  user's on-demand principle.
- `report`: for each check, over verified scans: P(rugged/dead | flag fired)
  vs P(rugged/dead | flag not fired), with counts. Shown in History screen
  header and CLI. When ≥300 verified scans exist, revisit: fit logistic
  regression on scan_json features (v1.1 milestone, user's math project).

## GUI (Flet)

1. **Splash** — Circuit Knight + "Coin Arena" on white, shows while engine
   opens DB and runs auto-verify (min 1.5s, max 6s; verify continues in
   background task if slower).
2. **Check** — mint input + Check button; verdict banner (red/amber/green
   tints); one row per finding: evidence text left, severity chip right
   (layout locked per approved mockup). Degraded-mode rows show "needs
   Helius key" chips linking to Settings.
3. **History** — table: time, symbol/mint (truncated), verdict, outcome
   (blank until verified). Header shows running hit-rate summary once ≥20
   verified scans exist.
4. **Settings** — Helius key field (stored in a local config file chmod 600,
   never in the repo or logs; validated with one test call on save), mode
   indicator (Full / Public-degraded), "Get a free key" link, data folder
   path, app version.

## Distribution

- Mac: `flet pack` → `Coin Arena.app`, zipped for download. Unsigned in v1
  (users right-click → Open on first launch; README documents this).
- Repo layout keeps `arena/` (engine+GUI) importable and platform-agnostic;
  a later `packaging/windows` GitHub Actions workflow adds the .exe.
- The app ships with NO API key. Error text is redacted with the same
  `api-key=***` pattern proven in the whale tracker.

## Error handling

- Engine never crashes a scan: per-check timeout/exception → INFO
  "check unavailable (reason)", verdict computed from completed checks, and
  the verdict banner notes "N of 6 checks unavailable".
- Invalid mint input → inline validation before any network call.
- No network → clear banner "offline — scan unavailable", app stays up.
- DB errors surface in a dismissible error bar; scans still display even if
  logging failed.

## Testing

- Engine: offline pytest suite, httpx.MockTransport fixtures per check —
  including real captured Helius/DexScreener response shapes (one `-m live`
  capture test, key required, skipped by default). Verdict table-driven
  tests. Verify-labeling tests with synthetic price histories.
- GUI: thin by design; smoke-tested manually per release. No GUI unit tests
  in v1.
- Fixtures must include at least one real rug's data (captured post-mortem)
  and one survivor, as end-to-end verdict regression tests.

## Milestones

1. Engine + CLI complete (usable by the user immediately, GUI-independent).
2. GUI shell + branding + packaging → shareable .app.
3. (v1.1, data-gated) Fitted probability model replacing hand thresholds at
   ≥300 verified scans; full PnL smart-money engine; Windows build.
