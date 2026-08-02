import flet as ft

from arena.flow.kelly import KellyInputs
from arena.flow.tips import recommend
from arena.gui import theme
from arena.gui.sizing_worker import run_kelly, run_tips

FIELDS = [
    ("hit_rate", "Hit rate (0-1)", "0.10"),
    ("winner_multiple", "Minimum winner multiple", "5.0"),
    ("tail_index", "Tail index alpha", "1.8"),
    ("max_drawdown", "Max drawdown (0-1)", "0.50"),
    ("ruin_tolerance", "Ruin tolerance (0-1)", "0.05"),
]


def build_sizing(page: ft.Page, on_back) -> ft.View:
    inputs = [ft.TextField(label=label, value=default, width=320)
              for _, label, default in FIELDS]
    compute_btn = ft.FilledButton("Compute size", bgcolor=theme.CYAN,
                                  color=theme.WHITE)
    tips_btn = ft.TextButton("Fetch live tips")
    out = ft.Column(spacing=theme.GAP, width=460)

    def error(message: str) -> None:
        out.controls.clear()
        out.controls.append(ft.Text(message, color=theme.VERDICT_COLORS["AVOID"]))
        page.update()

    def show_kelly(result) -> None:
        out.controls.clear()
        out.controls.append(ft.Text(
            f"Size: {result.f_constrained * 100:.1f}% of bankroll",
            size=20, weight=ft.FontWeight.W_500, color=theme.INK))
        out.controls.append(ft.Text(
            f"unconstrained Kelly {result.f_star * 100:.1f}%, "
            f"P(drawdown breach) {result.drawdown_prob * 100:.1f}%",
            size=12, color=theme.MUTED))
        for label, value in result.sensitivity:
            out.controls.append(ft.Text(f"{label}: {value * 100:.1f}%",
                                        size=13, color=theme.INK))
        out.controls.append(ft.Text(
            "Every input above is an assumption you supplied, not a measurement. "
            "The spread across those three rows is how much the answer depends "
            "on being right.", size=12, color=theme.MUTED))
        page.update()

    def show_tips(tips) -> None:
        out.controls.clear()
        out.controls.append(ft.Text("Jito landed tips (SOL)", size=16,
                                    weight=ft.FontWeight.W_500, color=theme.INK))
        out.controls.append(ft.Text(
            f"p50 {tips.p50:.6f}   p75 {tips.p75:.6f}   "
            f"p95 {tips.p95:.6f}   p99 {tips.p99:.6f}",
            size=13, color=theme.INK))
        out.controls.append(ft.Text(
            f"recommended: {recommend(tips, 'normal'):.6f} SOL — what is "
            "currently landing, not a guarantee of inclusion.",
            size=12, color=theme.MUTED))
        page.update()

    def do_compute(_) -> None:
        try:
            values = [float(f.value) for f in inputs]
        except (TypeError, ValueError):
            error("every field must be a number")
            return
        payload = KellyInputs(hit_rate=values[0], winner_multiple=values[1],
                              tail_index=values[2], max_drawdown=values[3],
                              ruin_tolerance=values[4])
        out.controls.clear()
        out.controls.append(ft.Text("simulating…", color=theme.MUTED))
        page.update()
        run_kelly(payload,
                  on_done=lambda r: page.run_thread(show_kelly, r),
                  on_error=lambda e: page.run_thread(
                      lambda exc=e: error(f"sizing failed: {exc}")))

    def do_tips(_) -> None:
        run_tips(on_done=lambda t: page.run_thread(show_tips, t),
                 on_error=lambda e: page.run_thread(
                     lambda: error("tips unavailable right now")))

    compute_btn.on_click = do_compute
    tips_btn.on_click = do_tips

    return ft.View(
        route="/sizing",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([
                ft.TextButton("Back", on_click=lambda _: on_back()),
                ft.Text("Sizing & tips", size=18, weight=ft.FontWeight.W_500,
                        color=theme.INK),
            ]),
            ft.Column(inputs + [ft.Row([compute_btn, tips_btn]), out],
                      spacing=theme.GAP,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ])
