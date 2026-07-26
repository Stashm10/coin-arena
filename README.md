# Coin Arena (engine preview)

Pre-buy rug checks for Solana meme coins. Paste a mint address, get a
verdict in seconds: 🔴 AVOID / 🟡 CAUTION / 🟢 NO RED FLAGS (which is not
the same as safe). Six checks: mint/freeze authorities, holder
concentration, launch bundling, dev history, funding trail, vitals.
Every scan is logged locally; `verify` labels what actually happened;
`report` shows which flags actually predicted rugs in YOUR data.

## Setup

    python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
    .venv/bin/python -m arena set-key YOUR_FREE_HELIUS_KEY   # helius.dev, free

No key? Scans still run in degraded public mode (3 of 6 checks).

## Use

    .venv/bin/python -m arena check <mint address>
    .venv/bin/python -m arena verify     # label past scans (24h+ old)
    .venv/bin/python -m arena report     # per-flag hit rates

## Tests

    .venv/bin/pytest             # offline, no network
    .venv/bin/pytest -m live -v  # real APIs, needs key

## Desktop app (Coin Arena GUI)

A windowed version of the checker — no terminal needed once it's running.

### Run it (development)

    python3 -m venv .venv && .venv/bin/pip install -e '.[gui,dev]'
    .venv/bin/python -m arena.gui

Paste a Solana mint, click Check. Add your free Helius key under ⚙ Settings
(or run in public mode with 3 of 6 checks). Get a key at https://helius.dev.

### Build a double-clickable Mac app

    .venv/bin/flet pack arena/gui/__main__.py --name "Coin Arena" \
        --add-data "arena/gui/assets:arena/gui/assets"

This produces `dist/Coin Arena.app`. It is unsigned, so on first launch
macOS will warn — right-click the app → Open → Open to allow it once.
No API key is bundled; each user adds their own under Settings.

## Honest caveats

- Both the CLI and the desktop app detect *mechanical* rug setups only.
  Neither can detect intent, social/Twitter exit scams, or a slow bleed.
  🟢 "NO RED FLAGS" means no *mechanical* rug setup was found — never "safe".
- Not financial advice. Neither the CLI nor the app trades; execution
  stays manual.
