import flet as ft

from arena.gui import theme
from arena.gui.logo import logo_image


def _door(title: str, subtitle: str, on_click) -> ft.FilledButton:
    return ft.FilledButton(
        width=380, height=76, bgcolor=theme.CYAN, on_click=lambda _: on_click(),
        content=ft.Column(
            spacing=2, alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(title, size=16, weight=ft.FontWeight.W_500,
                        color=theme.WHITE),
                ft.Text(subtitle, size=12, color=theme.WHITE, opacity=0.85),
            ]))


def build_mode_picker(page: ft.Page, on_rug_check, on_qme) -> ft.View:
    return ft.View(
        route="/modes",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=theme.PAD,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    logo_image(width=88),
                    ft.Text("Coin Arena", size=22, weight=ft.FontWeight.W_500,
                            color=theme.INK),
                    _door("Rug Pull Checker",
                          "Six checks on a coin before you buy", on_rug_check),
                    _door("Quant Microstructure Engine",
                          "Live exit signal for a coin you hold", on_qme),
                ])
        ])
