from pathlib import Path

import flet as ft

from arena.gui.app import main

if __name__ == "__main__":
    ft.app(target=main, assets_dir=str(Path(__file__).parent / "assets"))
