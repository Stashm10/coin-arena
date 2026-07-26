import flet as ft

from arena.gui.app import main
from arena.gui.logo import ASSET_DIR

if __name__ == "__main__":
    ft.app(target=main, assets_dir=str(ASSET_DIR))
