import flet as ft

from arena.engine import MINT_RE
from arena.flow.signal import (COOLING, DISCONNECTED, EXIT, HEATING,
                               SENSITIVITIES, WARMUP)
from arena.gui import theme
from arena.gui.live_worker import start_watch
from arena.settings import load_settings
from arena.thresholds import (QME_BASE_HAZARD_PCT_PER_HOUR,
                              QME_HAZARD_MULT_CONCENTRATED,
                              QME_HAZARD_MULT_CREATOR_SELLING,
                              QME_HAZARD_MULT_MINT_LIVE)

STATE_COLORS = {
    HEATING: theme.VERDICT_COLORS["NO_RED_FLAGS"],
    COOLING: theme.VERDICT_COLORS["CAUTION"],
    EXIT: theme.VERDICT_COLORS["AVOID"],
    WARMUP: theme.MUTED,
    DISCONNECTED: theme.VERDICT_COLORS["AVOID"],
}


def _readout(view):
    # Body column: [input row, hazard toggles row, readout column].
    return view.controls[1].controls[2]


def render_state(view, state, hazard_label: str | None = None) -> None:
    """Render a SignalState into the view's readout column. Module-level so
    tests can drive it directly without a socket.

    hazard_label, when given, replaces the default flat-base wording with the
    effective assumed hazard (base scaled by any active toggle multipliers).
    It must always describe an assumption, never a measurement.
    """
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
        label = hazard_label or (
            f"assumed crash hazard {QME_BASE_HAZARD_PCT_PER_HOUR:.0f}%/hr")
        out.controls.append(ft.Text(
            f"hold drift = {state.hold_drift * 3600:.2f}/hr  {label}",
            size=13, color=theme.INK))


def build_live(page: ft.Page, on_back, on_open_sizing) -> ft.View:
    mint_field = ft.TextField(label="Mint address you hold", width=380,
                              text_style=ft.TextStyle(font_family="monospace"))
    watch_btn = ft.FilledButton("Watch", bgcolor=theme.CYAN, color=theme.WHITE)
    sensitivity = ft.Dropdown(
        width=130, value="balanced",
        options=[ft.dropdown.Option(key=k, text=k.capitalize())
                 for k in SENSITIVITIES])
    out = ft.Column(spacing=theme.GAP, width=520)
    handle_box: dict = {"handle": None}

    # Manual hazard-multiplier toggles (Finding 2): lambda_c is an assumption
    # the trader supplies, never a measurement, so these are plain checkboxes
    # the user ticks about facts they know about the coin — no API calls, no
    # automatic scanning. Placed in the body column (not the header row) so
    # the header layout contract tests/test_gui_live.py relies on
    # (Back/title/spacer/sensitivity/Sizing at fixed indices) is untouched.
    mint_live_cb = ft.Checkbox(label="Mint authority still live", value=False)
    concentrated_cb = ft.Checkbox(label="Supply concentrated in few wallets",
                                  value=False)
    creator_selling_cb = ft.Checkbox(label="Creator wallet selling",
                                     value=False)
    toggles_row = ft.Row([mint_live_cb, concentrated_cb, creator_selling_cb],
                        alignment=ft.MainAxisAlignment.CENTER)

    def _active_multiplier_pairs() -> list[tuple[str, float]]:
        pairs = []
        if mint_live_cb.value:
            pairs.append(("mint authority live", QME_HAZARD_MULT_MINT_LIVE))
        if concentrated_cb.value:
            pairs.append(("concentrated supply", QME_HAZARD_MULT_CONCENTRATED))
        if creator_selling_cb.value:
            pairs.append(("creator selling", QME_HAZARD_MULT_CREATOR_SELLING))
        return pairs

    def _active_multipliers() -> list[float]:
        # Read fresh on every call (not cached) so a running watch's
        # per-evaluation hazard computation picks up a toggle flip live.
        return [m for _, m in _active_multiplier_pairs()]

    def _hazard_label() -> str:
        pairs = _active_multiplier_pairs()
        effective_pct = QME_BASE_HAZARD_PCT_PER_HOUR
        for _, m in pairs:
            effective_pct *= m
        if not pairs:
            return f"assumed crash hazard {effective_pct:.0f}%/hr"
        parts = ", ".join(f"{name} ×{m:g}" for name, m in pairs)
        return f"assumed crash hazard {effective_pct:.0f}%/hr ({parts})"

    def do_back(_) -> None:
        # A running watch holds a live socket + daemon thread that keeps
        # calling page.run_thread(_apply, ...) against this view even after
        # it's no longer on screen. Stop it here so navigating away actually
        # closes the connection instead of leaking it in the background. On
        # an OS window close (rather than Back), there is no do_back call —
        # the socket is instead closed by the daemon worker thread dying
        # with the process (see live_worker.WatchHandle / threading.Thread
        # daemon=True).
        if handle_box["handle"] is not None:
            handle_box["handle"].stop()
            handle_box["handle"] = None
        on_back()

    view = ft.View(
        route="/live",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([
                ft.TextButton("Back", on_click=do_back),
                ft.Text("Quant Microstructure Engine", size=18,
                        weight=ft.FontWeight.W_500, color=theme.INK),
                ft.Container(expand=True),
                sensitivity,
                ft.TextButton("Sizing", on_click=lambda _: on_open_sizing()),
            ]),
            ft.Column([
                ft.Row([mint_field, watch_btn],
                       alignment=ft.MainAxisAlignment.CENTER),
                toggles_row,
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
            on_state=lambda s: page.run_thread(_apply, s),
            get_multipliers=_active_multipliers)

    def _apply(state) -> None:
        render_state(view, state, _hazard_label())
        page.update()

    watch_btn.on_click = do_watch
    return view
