import flet as ft

from arena.gui import theme
from arena.gui.views.check import build_check
from arena.gui.views.history import build_history
from arena.gui.views.live import build_live
from arena.gui.views.mode_picker import build_mode_picker
from arena.gui.views.settings import build_settings
from arena.gui.views.splash import build_splash


def main(page: ft.Page) -> None:
    page.title = "Coin Arena"
    page.window.bgcolor = theme.WHITE
    page.window.width = 640
    page.window.height = 640

    def show_modes():
        page.views.clear()
        page.views.append(build_mode_picker(page, on_rug_check=show_check,
                                            on_qme=show_live))
        page.update()

    def show_check():
        page.views.clear()
        page.views.append(build_check(page, on_open_settings=show_settings,
                                      on_open_history=show_history,
                                      on_back=show_modes))
        page.update()

    def show_live():
        page.views.clear()
        page.views.append(build_live(page, on_back=show_modes))
        page.update()

    def show_history():
        page.views.append(build_history(page, on_back=show_check))
        page.update()

    def show_settings():
        page.views.append(build_settings(page, on_back=show_check))
        page.update()

    def show_splash():
        page.views.clear()
        page.views.append(build_splash(page, on_done=show_modes))
        page.update()

    show_splash()
