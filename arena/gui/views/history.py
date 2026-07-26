import flet as ft

from arena.gui import theme
from arena.store import Store

_LABEL_BTN = {1: "Rug", 0: "Clean", None: "Unsure"}


def set_label(db_path, mint: str, was_rug: int | None) -> None:
    """Persist a manual label. Separated for unit-testing without Flet."""
    store = Store(db_path / "arena.db" if db_path else None)
    try:
        store.set_manual_label(mint, was_rug)
    finally:
        store.close()


def build_history(page: ft.Page, on_back) -> ft.View:
    from arena.paths import data_dir
    ddir = data_dir()
    store = Store()
    rows = store.scans_for_history()
    counts = store.label_counts()
    store.close()

    summary = ft.Text(
        f"{counts['total_scans']} scans · {counts['labeled']} labeled "
        f"({counts['rugs']} rug / {counts['cleans']} clean) · "
        f"{counts['unlabeled']} unlabeled",
        size=13, color=theme.MUTED)
    hint = ft.Text(
        "Enough labeled coins — run  python -m arena.train  to update the model."
        if counts["labeled"] >= 20 else "",
        size=12, color=theme.CYAN)

    list_col = ft.Column(spacing=theme.GAP, scroll=ft.ScrollMode.AUTO, expand=True)

    def make_row(r):
        current = r["was_rug"]
        chips = ft.Row(spacing=4)

        def relabel(value):
            # value is 1 (Rug), 0 (Clean), or None (Unsure -> clears the label)
            def handler(_):
                set_label(ddir, r["mint"], value)
                _rebuild()
            return handler

        for val in (1, 0, None):
            active = (val == current)
            chips.controls.append(ft.TextButton(
                _LABEL_BTN[val],
                on_click=relabel(val),
                style=ft.ButtonStyle(
                    bgcolor=theme.CYAN if active else None,
                    color=theme.WHITE if active else theme.INK)))
        return ft.Row([
            ft.Text(r["symbol"] or "?", width=70, color=theme.INK),
            ft.Text((r["mint"][:6] + "…"), width=80, color=theme.MUTED, size=12),
            ft.Text(r["verdict"], width=110, color=theme.MUTED, size=12),
            ft.Container(expand=True),
            chips,
        ])

    def _rebuild():
        s = Store()
        rows2 = s.scans_for_history()
        c = s.label_counts()
        s.close()
        summary.value = (f"{c['total_scans']} scans · {c['labeled']} labeled "
                         f"({c['rugs']} rug / {c['cleans']} clean) · "
                         f"{c['unlabeled']} unlabeled")
        hint.value = ("Enough labeled coins — run  python -m arena.train  to "
                      "update the model." if c["labeled"] >= 20 else "")
        list_col.controls = [make_row(r) for r in rows2]
        page.update()

    list_col.controls = [make_row(r) for r in rows]

    return ft.View(
        route="/history",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([ft.TextButton("← Back", on_click=lambda _: on_back()),
                    ft.Container(expand=True),
                    ft.Text("History", size=20, weight=ft.FontWeight.W_500,
                            color=theme.INK)]),
            summary, hint, list_col,
        ],
    )
