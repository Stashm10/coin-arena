from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets"


def logo_path() -> str:
    return str(ASSET_DIR / "circuit_knight.svg")


def logo_image(width: int = 96):
    """Flet Image control for the logo. Imported lazily so tests and the
    engine never pull in flet."""
    import flet as ft
    return ft.Image(src=logo_path(), width=width, height=width)
