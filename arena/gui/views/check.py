import flet as ft

from arena.engine import MINT_RE
from arena.gui import theme
from arena.gui.scan_worker import run_scan
from arena.gui.viewmodel import row_views, unavailable_footer, verdict_view
from arena.model import model_info
from arena.rpc import redact
from arena.settings import load_settings


def build_check(page: ft.Page, on_open_settings, on_open_history) -> ft.View:
    mint_field = ft.TextField(label="Solana mint address", width=440,
                              text_style=ft.TextStyle(font_family="monospace"))
    check_btn = ft.FilledButton("Check", bgcolor=theme.CYAN, color=theme.WHITE)
    spinner = ft.ProgressRing(visible=False, width=18, height=18, color=theme.CYAN)
    results = ft.Column(spacing=theme.GAP, width=520)

    def render(result):
        results.controls.clear()
        v = verdict_view(result)
        banner = [ft.Text(v.label, size=18, weight=ft.FontWeight.W_500, color=v.color)]
        if v.caption:
            banner.append(ft.Text(v.caption, size=12, color=v.color))
        banner.append(ft.Text(v.subtitle, size=12, color=theme.MUTED))
        results.controls.append(ft.Container(
            bgcolor=theme.WHITE, border=ft.Border.all(1, v.color),
            border_radius=8, padding=theme.PAD, content=ft.Column(banner, spacing=2)))
        if result.rug_probability is not None:
            pct = round(result.rug_probability * 100, 1)
            n = (model_info() or {}).get("n_samples", 0)
            p = result.rug_probability
            mcolor = (theme.VERDICT_COLORS["AVOID"] if p >= 0.70
                      else theme.VERDICT_COLORS["CAUTION"] if p >= 0.35
                      else theme.VERDICT_COLORS["NO_RED_FLAGS"])
            results.controls.append(ft.Text(
                f"Model estimate: {pct}% rug risk (from {n} labeled coins)",
                color=mcolor, weight=ft.FontWeight.W_500))
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
        msg = redact(str(exc)) if isinstance(exc, ValueError) else f"scan failed: {redact(str(exc))}"
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

    header = ft.Row([
        ft.Text("Coin Arena", size=20, weight=ft.FontWeight.W_500, color=theme.INK),
        ft.Container(expand=True),
        ft.TextButton("History", on_click=lambda _: on_open_history()),
        ft.TextButton("Settings", on_click=lambda _: on_open_settings()),
    ])

    body = ft.Column(
        [
            ft.Row([mint_field, check_btn, spinner],
                   alignment=ft.MainAxisAlignment.CENTER),
            results,
        ],
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=theme.PAD,
    )

    return ft.View(
        route="/",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[header, body],
    )
