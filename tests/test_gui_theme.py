from pathlib import Path

from arena.gui import theme
from arena.gui.logo import logo_path
from arena.models import CHECK_NAMES  # noqa: F401 (import proves engine still importable)


def test_verdict_colors_cover_all_verdicts():
    assert set(theme.VERDICT_COLORS) == {"AVOID", "CAUTION", "NO_RED_FLAGS"}


def test_severity_colors_cover_all_severities():
    assert set(theme.SEVERITY_COLORS) == {"DISQUALIFIER", "WARNING", "PASS", "INFO"}


def test_primary_is_cyan():
    assert theme.CYAN == "#0891B2"


def test_logo_asset_exists():
    p = Path(logo_path())
    assert p.is_file() and p.suffix == ".svg"
    assert "0891B2" in p.read_text()  # cyan line art present
