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
                 for k in SENSITIVITIES])
    out = ft.Column(spacing=theme.GAP, width=520)
    handle_box: dict = {"handle": None}

    def do_back(_) -> None:
        # A running watch holds a live socket + daemon thread that keeps
        # calling page.run_thread(_apply, ...) against this view even after
        # it's no longer on screen. Stop it here so navigating away actually
        # closes the connection instead of leaking it in the background.
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
