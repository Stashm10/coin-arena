# Coin Arena GUI Implementation Plan (Milestone 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A distributable Flet desktop app ("Coin Arena") — splash → check → settings — that wraps the shipped engine so a non-technical user pastes a Solana mint and gets a rug verdict without a terminal.

**Architecture:** New `arena/gui/` package depending on the engine (never the reverse). Pure, unit-tested helper modules (theme, viewmodel, scan_worker) carry all the logic; the Flet view builders are thin presentation, manually smoke-tested. Scans run on a background thread with their own asyncio loop so the window never freezes.

**Tech Stack:** Flet (desktop GUI), plus the existing engine (httpx, rich-free core), pytest. Flet is a new `gui` optional-extra; the engine/CLI install stays lean.

**Spec:** `docs/superpowers/specs/2026-07-25-coin-arena-gui-design.md`

## Global Constraints

- Python 3.11+. New runtime dep `flet` lives ONLY in a `gui` optional-extra (`pip install -e '.[gui]'`); `arena/` engine modules never import flet, and `arena/gui/` never imports httpx/RPC/sqlite directly (it calls the engine).
- Screens this milestone: Splash, Check, Settings. No History, no launch-time verify.
- Branding: cyan `#0891B2` primary; ink `#0F172A` text; white surfaces; verdict colors red `#DC2626` (AVOID), amber `#D97706` (CAUTION), green `#059669` (NO_RED_FLAGS). Flat, no gradients. Circuit Knight logo = committed vector asset.
- Verdict copy verbatim: AVOID → "AVOID"; CAUTION → "CAUTION"; NO_RED_FLAGS → "NO RED FLAGS" and MUST carry the caption "no red flags ≠ safe".
- The Helius key is never rendered back after saving (show "key set ✓"); every error string shown in the UI passes through `arena.rpc.redact`.
- `scan_worker` is UI-agnostic (no flet import) so it stays unit-testable; the view makes its callbacks thread-safe.
- Default `pytest` run stays zero-network and now also GUI-renderer-free: no test may call `ft.app(...)` or open a window. Live tests remain `-m live` deselected.
- Commit after every task with trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Work in `/Users/romanstashkiv/coin_arena` on branch `feature/gui` (created from `main` at Task 1).
- Flet API note: target the installed Flet version. This plan's Flet control code (views, routing) is written against Flet's `page.views` navigation + `ft.app(target=...)` + `page.run_thread(...)` API. If the installed version's control names differ, ADAPT the control code to that version while preserving the layout, copy, colors, and behavior described — and verify by actually running the app. The pure modules (theme, viewmodel, scan_worker) are version-independent and their code is exact.

## File Structure

```
coin_arena/
├── pyproject.toml                    # Task 1 — add [gui] extra + assets packaging
├── arena/gui/
│   ├── __init__.py                   # Task 1 (empty)
│   ├── theme.py                      # Task 1 — color/spacing constants
│   ├── logo.py                       # Task 1 — logo control builder from asset
│   ├── assets/
│   │   └── circuit_knight.svg        # Task 1 — committed logo
│   ├── viewmodel.py                  # Task 2 — pure display transforms
│   ├── scan_worker.py                # Task 3 — bg-thread scan runner (no flet import)
│   ├── views/
│   │   ├── __init__.py               # Task 4 (empty)
│   │   ├── splash.py                 # Task 4
│   │   ├── settings.py               # Task 4
│   │   └── check.py                  # Task 5
│   ├── app.py                        # Task 5 — routing + shared state
│   └── __main__.py                   # Task 5 — python -m arena.gui
├── README.md                         # Task 6 — GUI section
└── tests/
    ├── test_gui_theme.py             # Task 1
    ├── test_gui_viewmodel.py         # Task 2
    └── test_gui_scan_worker.py       # Task 3
```

---

### Task 1: Scaffolding, theme, logo asset

**Files:**
- Modify: `pyproject.toml`
- Create: `arena/gui/__init__.py`, `arena/gui/theme.py`, `arena/gui/logo.py`, `arena/gui/assets/circuit_knight.svg`
- Test: `tests/test_gui_theme.py`

**Interfaces:**
- Produces:
  ```python
  # arena/gui/theme.py
  CYAN = "#0891B2"; INK = "#0F172A"; WHITE = "#FFFFFF"; MUTED = "#64748B"
  BORDER = "#CBD5E1"
  VERDICT_COLORS = {"AVOID": "#DC2626", "CAUTION": "#D97706", "NO_RED_FLAGS": "#059669"}
  SEVERITY_COLORS = {"DISQUALIFIER": "#DC2626", "WARNING": "#D97706",
                     "PASS": "#059669", "INFO": "#64748B"}
  PAD = 16; GAP = 8
  # arena/gui/logo.py
  ASSET_DIR: Path                        # arena/gui/assets
  def logo_path() -> str                 # absolute path to circuit_knight.svg
  def logo_image(width: int = 96): ...   # returns ft.Image of the logo (imports flet lazily)
  ```

- [ ] **Step 1: Branch + pyproject gui extra**

```bash
cd /Users/romanstashkiv/coin_arena && git checkout -b feature/gui
```

In `pyproject.toml`, add a `gui` extra to `[project.optional-dependencies]` (alongside the existing `dev`):
```toml
gui = ["flet>=0.24"]
```
And ensure the assets ship — under `[tool.setuptools]` add:
```toml
[tool.setuptools.package-data]
"arena.gui" = ["assets/*.svg"]
```
Add `"arena.gui"` and `"arena.gui.views"` to the existing `packages = [...]` list.

- [ ] **Step 2: Install the gui extra**

```bash
.venv/bin/pip install -e '.[gui,dev]'
```
Expected: flet installs. If flet's install is slow/heavy that's expected (it bundles a desktop runtime).
Create empty `arena/gui/__init__.py`.

- [ ] **Step 3: Commit the logo asset**

Create `arena/gui/assets/circuit_knight.svg` with this exact content (original line-art knight, cyan on white, PCB node pads):
```xml
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Coin Arena">
  <rect width="100" height="100" fill="#FFFFFF"/>
  <path d="M34 87 L36 84 L33 76 L37 66 L44 58 L42 52 L31 56 L25 48 L32 35 L42 26 L46 15 L51 24 L62 17 L59 30 L65 46 L66 62 L61 76 L64 84 L66 87 Z"
        fill="none" stroke="#0891B2" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="46" cy="34" r="2.8" fill="#0891B2"/>
  <path d="M45 43 L52 45 L56 52" fill="none" stroke="#06B6D4" stroke-width="2.4" stroke-linecap="round"/>
  <circle cx="62" cy="17" r="3.2" fill="#FFFFFF" stroke="#0891B2" stroke-width="2"/>
  <circle cx="46" cy="15" r="3.2" fill="#FFFFFF" stroke="#0891B2" stroke-width="2"/>
  <circle cx="25" cy="48" r="3.2" fill="#FFFFFF" stroke="#0891B2" stroke-width="2"/>
  <circle cx="66" cy="62" r="3.2" fill="#FFFFFF" stroke="#0891B2" stroke-width="2"/>
</svg>
```

- [ ] **Step 4: Write the failing test**

`tests/test_gui_theme.py`:
```python
from pathlib import Path

from arena.gui import theme
from arena.gui.logo import logo_path
from arena.models import CHECK_NAMES  # noqa: F401 (import proves engine still importable)


def test_verdict_colors_cover_all_verdicts():
    assert set(theme.VERDICT_COLORS) == {"AVOID", "CAUTION", "NO_RED_FLAGS"}


def test_severity_colors_cover_all_severities():
    assert set(theme.SEVERITY_COLORS) == {"DISQUALIFIER", "WARNING", "PASS", "INFO"}


def test_primary_is_cyan():
    assert theme.CYAN == "#0891B2"


def test_logo_asset_exists():
    p = Path(logo_path())
    assert p.is_file() and p.suffix == ".svg"
    assert "0891B2" in p.read_text()  # cyan line art present
```

- [ ] **Step 5: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_theme.py -v`
Expected: FAIL — `ModuleNotFoundError: arena.gui.theme`.

- [ ] **Step 6: Implement theme.py and logo.py**

`arena/gui/theme.py`:
```python
CYAN = "#0891B2"
INK = "#0F172A"
WHITE = "#FFFFFF"
MUTED = "#64748B"
BORDER = "#CBD5E1"

VERDICT_COLORS = {"AVOID": "#DC2626", "CAUTION": "#D97706", "NO_RED_FLAGS": "#059669"}
SEVERITY_COLORS = {"DISQUALIFIER": "#DC2626", "WARNING": "#D97706",
                   "PASS": "#059669", "INFO": "#64748B"}

PAD = 16
GAP = 8
```

`arena/gui/logo.py`:
```python
from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets"


def logo_path() -> str:
    return str(ASSET_DIR / "circuit_knight.svg")


def logo_image(width: int = 96):
    """Flet Image control for the logo. Imported lazily so tests and the
    engine never pull in flet."""
    import flet as ft
    return ft.Image(src=logo_path(), width=width, height=width)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_gui_theme.py -v` — Expected: 4 PASSED. Full suite green.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml arena/gui/ tests/test_gui_theme.py
git commit -m "feat: gui scaffolding, theme, and logo asset"
```

---

### Task 2: Viewmodel (pure display transforms)

**Files:**
- Create: `arena/gui/viewmodel.py`
- Test: `tests/test_gui_viewmodel.py`

**Interfaces:**
- Consumes: `theme` (Task 1); `ScanResult`/`Finding` (engine).
- Produces:
  ```python
  @dataclass
  class VerdictView:
      label: str        # "AVOID" | "CAUTION" | "NO RED FLAGS"
      color: str        # hex from theme.VERDICT_COLORS
      caption: str | None  # "no red flags ≠ safe" for NO_RED_FLAGS else None
      subtitle: str     # "{symbol or short mint} · scanned in {duration}s"

  @dataclass
  class RowView:
      severity: str
      color: str        # theme.SEVERITY_COLORS[severity]
      evidence: str
      dim: bool         # True for INFO

  def verdict_view(result: ScanResult) -> VerdictView
  def row_views(result: ScanResult) -> list[RowView]     # engine order preserved
  def unavailable_footer(result: ScanResult) -> str | None
      # "N of 6 checks unavailable — add your Helius key in Settings" when >0 else None
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_gui_viewmodel.py`:
```python
from arena.gui import theme
from arena.gui.viewmodel import (row_views, unavailable_footer, verdict_view)
from arena.models import Finding, ScanResult


def result(verdict="AVOID", findings=None, unavailable=0, symbol="TEST", dur=1.5):
    return ScanResult(mint="M" * 44, verdict=verdict,
                      findings=findings or [Finding("authorities", "PASS", "ok", {})],
                      unavailable=unavailable, price_usd=None, symbol=symbol,
                      duration_s=dur)


def test_verdict_view_avoid():
    v = verdict_view(result("AVOID"))
    assert v.label == "AVOID" and v.color == theme.VERDICT_COLORS["AVOID"]
    assert v.caption is None
    assert "TEST" in v.subtitle and "1.5" in v.subtitle


def test_verdict_view_clean_has_caption():
    v = verdict_view(result("NO_RED_FLAGS"))
    assert v.label == "NO RED FLAGS"
    assert v.caption == "no red flags ≠ safe"


def test_verdict_view_no_symbol_uses_short_mint():
    v = verdict_view(result("CAUTION", symbol=None))
    assert v.label == "CAUTION"
    assert "MMMM" in v.subtitle  # falls back to a truncated mint


def test_row_views_preserve_order_and_dim_info():
    findings = [Finding("authorities", "DISQUALIFIER", "bad", {}),
                Finding("vitals", "INFO", "age 3m", {})]
    rows = row_views(result(findings=findings))
    assert [r.severity for r in rows] == ["DISQUALIFIER", "INFO"]
    assert rows[0].color == theme.SEVERITY_COLORS["DISQUALIFIER"]
    assert rows[0].dim is False and rows[1].dim is True


def test_unavailable_footer():
    assert unavailable_footer(result(unavailable=0)) is None
    msg = unavailable_footer(result(unavailable=3))
    assert "3 of 6" in msg and "Settings" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_gui_viewmodel.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement arena/gui/viewmodel.py**

```python
from dataclasses import dataclass

from arena.gui import theme
from arena.models import ScanResult

_LABELS = {"AVOID": "AVOID", "CAUTION": "CAUTION", "NO_RED_FLAGS": "NO RED FLAGS"}


@dataclass
class VerdictView:
    label: str
    color: str
    caption: str | None
    subtitle: str


@dataclass
class RowView:
    severity: str
    color: str
    evidence: str
    dim: bool


def verdict_view(result: ScanResult) -> VerdictView:
    name = result.symbol or (result.mint[:8] + "…")
    return VerdictView(
        label=_LABELS[result.verdict],
        color=theme.VERDICT_COLORS[result.verdict],
        caption="no red flags ≠ safe" if result.verdict == "NO_RED_FLAGS" else None,
        subtitle=f"{name} · scanned in {result.duration_s}s",
    )


def row_views(result: ScanResult) -> list[RowView]:
    return [RowView(severity=f.severity,
                    color=theme.SEVERITY_COLORS.get(f.severity, theme.MUTED),
                    evidence=f.evidence, dim=(f.severity == "INFO"))
            for f in result.findings]


def unavailable_footer(result: ScanResult) -> str | None:
    if result.unavailable <= 0:
        return None
    return (f"{result.unavailable} of 6 checks unavailable — "
            "add your Helius key in Settings")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_viewmodel.py -v` — Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add arena/gui/viewmodel.py tests/test_gui_viewmodel.py
git commit -m "feat: gui viewmodel display transforms"
```

---

### Task 3: Scan worker (background thread, UI-agnostic)

**Files:**
- Create: `arena/gui/scan_worker.py`
- Test: `tests/test_gui_scan_worker.py`

**Interfaces:**
- Consumes: `check_mint` (engine), `Store`, `Settings`.
- Produces:
  ```python
  def run_scan(mint: str, settings: Settings,
               on_done: Callable[[ScanResult], None],
               on_error: Callable[[Exception], None],
               scan_fn: Callable[[str, Settings], ScanResult] | None = None
               ) -> threading.Thread
      # spawns a daemon thread; calls on_done(result) or on_error(exc) FROM that
      # thread; returns the thread (started). scan_fn injectable for tests;
      # default runs engine.check_mint on a fresh asyncio loop with its own
      # AsyncClient + Store.
  ```
  NOTE (for the view author, Task 5): `on_done`/`on_error` fire on the worker thread — the view MUST wrap its UI updates with `page.run_thread(...)` to stay thread-safe. `scan_worker` itself imports no flet.
- No flet import in this module (keeps it unit-testable and enforces the engine/GUI boundary).

- [ ] **Step 1: Write the failing tests**

`tests/test_gui_scan_worker.py`:
```python
import threading

from arena.gui.scan_worker import run_scan
from arena.models import Finding, ScanResult
from arena.settings import Settings


def _result():
    return ScanResult("M" * 44, "AVOID",
                      [Finding("authorities", "DISQUALIFIER", "x", {})],
                      0, None, "T", 1.0)


def test_on_done_called_with_result():
    done = threading.Event()
    holder = {}

    def on_done(r):
        holder["r"] = r
        done.set()

    t = run_scan("mint", Settings("k"), on_done, lambda e: None,
                 scan_fn=lambda m, s: _result())
    assert done.wait(timeout=5)
    t.join(timeout=5)
    assert holder["r"].verdict == "AVOID"


def test_on_error_called_on_exception():
    failed = threading.Event()
    holder = {}

    def on_error(exc):
        holder["exc"] = exc
        failed.set()

    def boom(m, s):
        raise RuntimeError("scan blew up")

    run_scan("mint", Settings(None), lambda r: None, on_error, scan_fn=boom)
    assert failed.wait(timeout=5)
    assert isinstance(holder["exc"], RuntimeError)


def test_returns_started_thread():
    t = run_scan("mint", Settings("k"), lambda r: None, lambda e: None,
                 scan_fn=lambda m, s: _result())
    assert isinstance(t, threading.Thread)
    t.join(timeout=5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_gui_scan_worker.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement arena/gui/scan_worker.py**

```python
import asyncio
import threading
from typing import Callable

import httpx

from arena.engine import check_mint
from arena.models import ScanResult
from arena.settings import Settings
from arena.store import Store


async def _scan_async(mint: str, settings: Settings) -> ScanResult:
    store = Store()
    try:
        async with httpx.AsyncClient() as client:
            return await check_mint(mint, settings, store, client)
    finally:
        store.close()


def _default_scan(mint: str, settings: Settings) -> ScanResult:
    # Fresh event loop per call — safe because this runs on a worker thread.
    return asyncio.run(_scan_async(mint, settings))


def run_scan(mint: str, settings: Settings,
             on_done: Callable[[ScanResult], None],
             on_error: Callable[[Exception], None],
             scan_fn: Callable[[str, Settings], ScanResult] | None = None
             ) -> threading.Thread:
    """Run a scan off the UI thread. Calls on_done/on_error FROM the worker
    thread — the caller (view) must marshal UI updates back with
    page.run_thread(). No flet import here on purpose."""
    fn = scan_fn or _default_scan

    def worker() -> None:
        try:
            on_done(fn(mint, settings))
        except Exception as exc:  # includes ValueError (bad mint)
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_gui_scan_worker.py -v` — Expected: 3 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/gui/scan_worker.py tests/test_gui_scan_worker.py
git commit -m "feat: background-thread scan worker"
```

---

### Task 4: Splash + Settings views

**Files:**
- Create: `arena/gui/views/__init__.py` (empty), `arena/gui/views/splash.py`, `arena/gui/views/settings.py`
- Test: manual smoke (Task 5 wires them into the running app; these builders have no pure logic beyond what viewmodel/settings already test).

**Interfaces:**
- Consumes: `theme`, `logo` (Task 1); `load_settings`, `save_key`, `Settings` (engine); `paths.data_dir`.
- Produces:
  ```python
  # splash.py
  def build_splash(page, on_done) -> "ft.View"
      # a View showing the logo + "Coin Arena"; schedules on_done() after ~1.5s
  # settings.py
  def build_settings(page, on_back) -> "ft.View"
      # key field (password), Save button, mode indicator, helius.dev link,
      # data-dir path, version; Back calls on_back()
  ```
- Flet API note applies (see Global Constraints): adapt control names to the installed Flet version, preserve behavior/copy/colors.

- [ ] **Step 1: Implement splash.py**

```python
import threading

import flet as ft

from arena.gui import theme
from arena.gui.logo import logo_image

SPLASH_SECONDS = 1.5


def build_splash(page: ft.Page, on_done) -> ft.View:
    def go():
        page.run_thread(on_done)
    threading.Timer(SPLASH_SECONDS, go).start()
    return ft.View(
        route="/splash",
        bgcolor=theme.WHITE,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    logo_image(width=120),
                    ft.Text("Coin Arena", size=24, weight=ft.FontWeight.W_500,
                            color=theme.INK),
                ],
            )
        ],
    )
```

- [ ] **Step 2: Implement settings.py**

```python
import flet as ft

from arena.gui import theme
from arena.paths import data_dir
from arena.settings import load_settings, save_key


def build_settings(page: ft.Page, on_back) -> ft.View:
    settings = load_settings()
    status = ft.Text(
        "Full mode (Helius key set)" if settings.mode == "full"
        else "Public mode — 3 of 6 checks limited",
        color=theme.MUTED, size=13)
    key_field = ft.TextField(label="Helius API key", password=True,
                             can_reveal_password=True, width=420)
    saved_note = ft.Text("", color=theme.VERDICT_COLORS["NO_RED_FLAGS"], size=13)

    def do_save(_):
        if not key_field.value.strip():
            saved_note.value = "enter a key first"
            saved_note.color = theme.VERDICT_COLORS["AVOID"]
            page.update()
            return
        save_key(key_field.value.strip())
        key_field.value = ""
        saved_note.value = "key set ✓"
        saved_note.color = theme.VERDICT_COLORS["NO_RED_FLAGS"]
        status.value = "Full mode (Helius key set)"
        page.update()

    return ft.View(
        route="/settings",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([ft.TextButton("← Back", on_click=lambda _: on_back())]),
            ft.Text("Settings", size=20, weight=ft.FontWeight.W_500, color=theme.INK),
            status,
            key_field,
            ft.Row([ft.FilledButton("Save", on_click=do_save,
                                    bgcolor=theme.CYAN, color=theme.WHITE),
                    saved_note]),
            ft.Markdown("[Get a free key at helius.dev](https://helius.dev)",
                        on_tap_link=lambda e: page.launch_url(e.data)),
            ft.Text(f"Data folder: {data_dir()}", color=theme.MUTED, size=12,
                    selectable=True),
            ft.Text("Coin Arena — milestone 2", color=theme.MUTED, size=12),
        ],
    )
```
Note: the footer renders a static "Coin Arena — milestone 2" string — do not add a version module this milestone.

- [ ] **Step 3: Create empty views/__init__.py and verify imports**

```bash
touch arena/gui/views/__init__.py
.venv/bin/python -c "from arena.gui.views import splash, settings; print('import ok')"
```
Expected: `import ok` (proves the flet controls construct at import time without a running app; fix any AttributeError by adapting to the installed Flet API per the version note).

- [ ] **Step 4: Full offline suite still green**

Run: `.venv/bin/pytest`
Expected: all prior tests pass, zero network, no window opened.

- [ ] **Step 5: Commit**

```bash
git add arena/gui/views/
git commit -m "feat: splash and settings views"
```

---

### Task 5: Check view + app routing + entry point

**Files:**
- Create: `arena/gui/views/check.py`, `arena/gui/app.py`, `arena/gui/__main__.py`
- Test: manual smoke with screenshots (below) + full offline suite green.

**Interfaces:**
- Consumes: `theme`, `viewmodel`, `scan_worker`, `logo`; `views/splash.py`, `views/settings.py`; `load_settings`; `arena.rpc.redact`; `engine.MINT_RE`.
- Produces:
  ```python
  # check.py
  def build_check(page, on_open_settings) -> "ft.View"
  # app.py
  def main(page) -> None          # sets up routing, starts at splash
  # __main__.py
  # ft.app(target=main)
  ```
- Flet API note applies.

- [ ] **Step 1: Implement check.py**

```python
import flet as ft

from arena.engine import MINT_RE
from arena.gui import theme
from arena.gui.scan_worker import run_scan
from arena.gui.viewmodel import row_views, unavailable_footer, verdict_view
from arena.rpc import redact
from arena.settings import load_settings


def build_check(page: ft.Page, on_open_settings) -> ft.View:
    mint_field = ft.TextField(label="Solana mint address", width=440,
                              text_style=ft.TextStyle(font_family="monospace"))
    check_btn = ft.FilledButton("Check", bgcolor=theme.CYAN, color=theme.WHITE)
    spinner = ft.ProgressRing(visible=False, width=18, height=18, color=theme.CYAN)
    results = ft.Column(spacing=theme.GAP)

    def render(result):
        results.controls.clear()
        v = verdict_view(result)
        banner = [ft.Text(v.label, size=18, weight=ft.FontWeight.W_500, color=v.color)]
        if v.caption:
            banner.append(ft.Text(v.caption, size=12, color=v.color))
        banner.append(ft.Text(v.subtitle, size=12, color=theme.MUTED))
        results.controls.append(ft.Container(
            bgcolor=theme.WHITE, border=ft.border.all(1, v.color),
            border_radius=8, padding=theme.PAD, content=ft.Column(banner, spacing=2)))
        for r in row_views(result):
            results.controls.append(ft.Row([
                ft.Text(r.severity, width=120, color=r.color,
                        weight=ft.FontWeight.W_500,
                        opacity=0.6 if r.dim else 1.0),
                ft.Text(r.evidence, color=theme.INK, expand=True,
                        opacity=0.6 if r.dim else 1.0)]))
        footer = unavailable_footer(result)
        if footer:
            results.controls.append(ft.Text(footer, size=12, color=theme.MUTED))

    def finish(result):
        render(result)
        spinner.visible = False
        check_btn.disabled = False
        page.update()

    def fail(exc):
        results.controls.clear()
        msg = str(exc) if isinstance(exc, ValueError) else f"scan failed: {redact(str(exc))}"
        results.controls.append(ft.Text(msg, color=theme.VERDICT_COLORS["AVOID"]))
        spinner.visible = False
        check_btn.disabled = False
        page.update()

    def do_check(_):
        mint = (mint_field.value or "").strip()
        if not MINT_RE.match(mint):
            results.controls.clear()
            results.controls.append(ft.Text("not a valid Solana mint address",
                                            color=theme.VERDICT_COLORS["AVOID"]))
            page.update()
            return
        results.controls.clear()
        spinner.visible = True
        check_btn.disabled = True
        page.update()
        run_scan(mint, load_settings(),
                 on_done=lambda r: page.run_thread(finish, r),
                 on_error=lambda e: page.run_thread(fail, e))

    check_btn.on_click = do_check

    return ft.View(
        route="/",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([ft.Text("Coin Arena", size=20, weight=ft.FontWeight.W_500,
                            color=theme.INK),
                    ft.Container(expand=True),
                    ft.TextButton("⚙ Settings", on_click=lambda _: on_open_settings())]),
            ft.Row([mint_field, check_btn, spinner]),
            results,
        ],
    )
```
Flet note: `page.run_thread(fn, *args)` marshals the callback onto the UI thread; if the installed Flet exposes this differently (e.g. `page.run_task` for coroutines), use the version's thread-safe update mechanism — the requirement is that `finish`/`fail` run on the UI thread.

- [ ] **Step 2: Implement app.py**

```python
import flet as ft

from arena.gui import theme
from arena.gui.views.check import build_check
from arena.gui.views.settings import build_settings
from arena.gui.views.splash import build_splash


def main(page: ft.Page) -> None:
    page.title = "Coin Arena"
    page.bgcolor = theme.WHITE
    page.window_width = 640
    page.window_height = 640

    def show_check():
        page.views.clear()
        page.views.append(build_check(page, on_open_settings=show_settings))
        page.update()

    def show_settings():
        page.views.append(build_settings(page, on_back=show_check))
        page.update()

    def show_splash():
        page.views.clear()
        page.views.append(build_splash(page, on_done=show_check))
        page.update()

    show_splash()
```

- [ ] **Step 3: Implement __main__.py**

```python
import flet as ft

from arena.gui.app import main

if __name__ == "__main__":
    ft.app(target=main)
```

- [ ] **Step 4: Verify imports + full offline suite**

```bash
.venv/bin/python -c "from arena.gui import app; from arena.gui.views import check; print('import ok')"
.venv/bin/pytest
```
Expected: `import ok`; suite green, zero network, no window opened by tests.

- [ ] **Step 5: Manual smoke with screenshots**

```bash
.venv/bin/python -m arena.gui
```
Do the following and capture a screenshot of each:
1. Splash appears with the Circuit Knight logo, then auto-advances to Check (~1.5s).
2. Paste a known-clean mint (`SYePbBxKaVhxuDsq9v4CeQaxUJtSV1pXKNzF9bGpump`), click Check: spinner shows, then a green/amber verdict panel + six finding rows. Window stayed responsive during the scan.
3. Paste a known-bundled mint (`HCjg6jUff3MZW8oE4ZPJzG24awxB5aQCKCRQkedNpump`): a red AVOID panel with the bundle DISQUALIFIER row.
4. Paste garbage ("notamint"): inline "not a valid Solana mint address", no crash.
5. Click ⚙ Settings: key field, mode indicator, helius.dev link, data-folder path. Save a key → "key set ✓", mode flips to Full. Back → Check.

Record in the report which of these passed and attach/describe the screenshots. If the running app reveals a Flet API mismatch, adapt the control code to the installed version (preserving behavior) and note what changed.

- [ ] **Step 6: Commit**

```bash
git add arena/gui/views/check.py arena/gui/app.py arena/gui/__main__.py
git commit -m "feat: check view, app routing, and GUI entry point"
```

---

### Task 6: Packaging recipe + README

**Files:**
- Modify: `README.md`
- Create: nothing else (packaging is a documented recipe this milestone, not an artifact)

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the GUI section to README.md**

Append to `README.md`:
```markdown
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

### Honest caveats

- 🟢 "NO RED FLAGS" means no *mechanical* rug setup was found — never "safe".
  It cannot detect intent, social/exit scams, or a slow bleed.
- Not financial advice. The app never trades; execution stays manual.
```

- [ ] **Step 2: Verify the pack recipe (best-effort)**

```bash
.venv/bin/flet pack arena/gui/__main__.py --name "Coin Arena" --add-data "arena/gui/assets:arena/gui/assets"
ls -la "dist/Coin Arena.app" 2>&1 | head -1
```
Expected: a `dist/Coin Arena.app` bundle is produced. If `flet pack` fails in this environment (toolchain/signing issues are common and out of scope for a v1), record the exact error in the report and leave the documented recipe in place — the README run-script path is the guaranteed one this milestone. Do NOT commit the `dist/` output (add `dist/` and `build/` to `.gitignore` if not already ignored).

- [ ] **Step 3: Ensure build artifacts are gitignored**

Confirm `.gitignore` contains `dist/` and `build/`; add them if missing:
```bash
grep -qxF 'dist/' .gitignore || printf 'dist/\nbuild/\n' >> .gitignore
```

- [ ] **Step 4: Full suite green + commit**

Run: `.venv/bin/pytest` — Expected: all green.
```bash
git add README.md .gitignore
git commit -m "docs: GUI run + packaging instructions"
```

---

## Verification against spec (after all tasks)

1. `.venv/bin/pytest` — green, zero network, no window opened by tests.
2. `.venv/bin/python -m arena.gui` — splash → check; clean mint → green panel with "no red flags ≠ safe"; bundled mint → red AVOID; bad input → inline error; Settings saves a key (never echoes it) and flips to Full mode. Window responsive during scans.
3. `grep -rn "import flet" arena/*.py arena/checks/*.py` — no matches (engine never imports flet); `grep -rn "import httpx" arena/gui` — only scan_worker.
4. `git status` — clean; no `dist/`, `build/`, `config.json`, or `arena.db` tracked.
