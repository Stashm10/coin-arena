import threading

import flet as ft

from arena.gui import theme
from arena.gui.logo import logo_image

SPLASH_SECONDS = 1.5


def build_splash(page: ft.Page, on_done) -> ft.View:
    def go():
        page.run_thread(on_done)
    t = threading.Timer(SPLASH_SECONDS, go)
    t.daemon = True
    t.start()
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
