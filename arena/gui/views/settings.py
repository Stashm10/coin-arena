import flet as ft

from arena.gui import theme
from arena.paths import data_dir
from arena.rpc import redact
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
        key_value = (key_field.value or "").strip()
        if not key_value:
            saved_note.value = "enter a key first"
            saved_note.color = theme.VERDICT_COLORS["AVOID"]
            page.update()
            return
        try:
            save_key(key_value)
        except OSError as exc:
            saved_note.value = f"could not save key: {redact(str(exc))}"
            saved_note.color = theme.VERDICT_COLORS["AVOID"]
            page.update()
            return
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
