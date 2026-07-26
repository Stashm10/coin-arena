# Coin Arena GUI — Design Spec (Milestone 2)

**Date:** 2026-07-25
**Status:** Approved in brainstorm; pending user review of this document
**Builds on:** Milestone 1 (engine + CLI), shipped to main 2026-07-25.

## Purpose

Wrap the already-shipped, already-tested Coin Arena analysis engine in a
distributable desktop GUI so a non-technical user can paste a Solana mint
and get a rug verdict without touching a terminal. This milestone delivers
the smallest genuinely shareable app: a splash screen, the main check
screen, and a settings screen for the Helius key.

## Key decisions (made with user)

| Decision | Choice |
|---|---|
| Framework | Flet (Python → native desktop window) |
| Async model | Scans run on a background worker thread with its own asyncio loop; UI shows a spinner and stays responsive; thread-safe callback updates the UI |
| Screens this milestone | Splash, Check, Settings (History deferred) |
| Engine coupling | GUI imports and calls the engine unchanged; never touches httpx/RPC/SQLite directly |
| Branding | Circuit Knight logo (committed vector asset), "Coin Arena", white + cyan (#0891B2), flat, no flashy effects |
| Key handling | Settings screen saves via existing `save_key` (chmod 600); key never rendered back; errors pass through `redact()` |
| Launch-time verify | None this milestone (instant startup; `verify` stays a CLI action) |
| Packaging | Verify via `flet run` first; then documented `flet pack` → `Coin Arena.app`. Windows later, config-only |
| Testing | GUI layer thin + manually smoke-tested (driven + screenshotted); all logic stays in the engine's existing test suite |

## Architecture

The engine is a pure library with zero GUI dependencies (established in
milestone 1). The GUI is a new `arena/gui/` package that depends on the
engine, never the reverse.

```
arena/gui/
├── __init__.py
├── __main__.py        # python -m arena.gui → ft.app(target=main)
├── app.py             # main(page): routing between the three views, shared state
├── theme.py           # colors (cyan #0891B2, verdict colors), fonts, spacing constants
├── logo.py            # Circuit Knight as a Flet vector/Image control (from assets/)
├── scan_worker.py     # run_scan_in_thread(mint, on_done, on_error) — bg thread + asyncio loop
├── views/
│   ├── splash.py      # build_splash(page) — logo + name, ~1.5s
│   ├── check.py       # build_check(page, ...) — input, Check button, verdict + findings
│   └── settings.py    # build_settings(page, ...) — key field, mode indicator, links
└── assets/
    └── circuit_knight.svg   # committed logo asset
```

New runtime dependency: `flet` (added to a `gui` optional-extra in
pyproject, so the engine/CLI install stays lean).

## Async model (the load-bearing detail)

Flet's UI runs on the main thread; a scan is async network I/O taking
~2–10s. `scan_worker.run_scan(mint, settings, on_done, on_error)`:

- spawns a `threading.Thread`, which creates a fresh event loop
  (`asyncio.new_event_loop`), opens its own `httpx.AsyncClient` and `Store`,
  runs `engine.check_mint(...)`, closes both, and marshals the result back
  to the UI thread via `page.run_thread` (or an equivalent thread-safe
  `page.update()` callback).
- The Check view disables the Check button and shows a spinner on click,
  then re-enables and renders the verdict (or an inline error) on callback.
- `check_mint` already never raises for network/API failures; `on_error`
  handles the ValueError (bad mint) and any unexpected exception, showing
  redacted inline text — never a crash dialog.

## Screens

### Splash
Circuit Knight logo + "Coin Arena" wordmark, centered on white, shown for
~1.5s (timer), then routes to Check. No network, no verify.

### Check (main)
- Mint text field (monospace) + "Check" button.
- On submit: validate non-empty; disable button + spinner; run scan.
- Result: verdict banner — red (AVOID) / amber (CAUTION) / green
  (NO_RED_FLAGS), green captioned "no red flags ≠ safe" — with symbol and
  scan duration; then one row per finding: severity chip (colored) + evidence
  text, in the fixed engine order. INFO rows dim. A footer line when
  `unavailable > 0`: "N of 6 checks unavailable — add your Helius key in
  Settings".
- Invalid mint → inline red helper text under the field, no scan.
- A "⚙ Settings" button (top-right) routes to Settings.
- Untrusted strings (symbol, evidence) are escaped before display (Flet Text
  is not markup-parsed by default, so this is inherently safe, but confirm
  no markdown/rich control is used for those fields).

### Settings
- Password-style field to paste the Helius key; "Save" calls `save_key` and
  then shows "key set ✓" (never echoes the value). If a key is already set,
  the field shows empty with a "key set ✓" indicator rather than the value.
- Mode indicator: "Full mode (Helius key set)" or "Public mode — 3 of 6
  checks limited".
- A "Get a free key at helius.dev" link (opens in browser).
- Data folder path (from `paths.data_dir()`), shown as read-only text.
- App version. Back button → Check.

## Branding / theme

`theme.py` centralizes: cyan `#0891B2` (primary/accent), white surfaces,
ink `#0F172A` text, verdict colors (red `#DC2626`, amber `#D97706`, green
`#059669`). Flat design, no gradients/shadows beyond Flet defaults. The
Circuit Knight logo is a committed SVG asset (original line-art knight with
PCB node pads, cyan on white) rendered via a Flet `Image`/vector control;
it is also the window icon where Flet supports it.

## Error handling

- Bad mint → inline field error, no scan, app stays up.
- Engine/network failure → `check_mint` returns a result with INFO
  "unavailable" findings (never raises for those); the UI renders them
  normally. Any truly unexpected exception in the worker → `on_error`
  shows a dismissible redacted message; the window never crashes.
- Missing/invalid key → app runs in public mode; Settings makes fixing it
  obvious. Saving an invalid key still saves it. The "validate" ping
  (one `getSlot`) that would show "saved, but validation failed" is
  deferred to fast-follow (see Out of scope below); today Settings just
  shows Full/Public mode after save.

## Packaging

1. `flet run arena/gui` (or `python -m arena.gui`) verified working +
   screenshotted.
2. Documented `flet pack` recipe → `Coin Arena.app` (unsigned; README notes
   right-click→Open on first launch). No key bundled.
3. Windows `.exe` remains a later config-only addition (out of scope).

## Testing

- GUI is thin presentation over the tested engine; no new business logic.
- Manual smoke: launch app, scan a known clean mint and a known bundled
  mint, confirm verdict rendering, spinner behavior, Settings save/mode
  switch; capture screenshots. Driven by the implementer/controller.
- Any pure helper added in the GUI (e.g. a verdict→color map in `theme.py`,
  or a findings→display-rows transform) gets a small unit test so the
  logic-ish bits aren't untested even though rendering is manual.

## Out of scope (fast-follow / later milestones)

- History screen (CLI `report`/`history` still available).
- Launch-time auto-verify.
- Smart-money display polish beyond the existing vitals line.
- Windows/Linux builds.
- Code signing / notarization.
- Settings key-validation ping (spec's "saved, but validation failed"
  feedback) — deferred; the CLI `set-key` validates, and Settings shows
  Full/Public mode.
