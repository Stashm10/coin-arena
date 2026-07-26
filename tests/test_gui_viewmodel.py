from arena.gui import theme
from arena.gui.viewmodel import (row_views, unavailable_footer, verdict_view)
from arena.models import Finding, ScanResult


def result(verdict="AVOID", findings=None, unavailable=0, symbol="TEST", dur=1.5):
    return ScanResult(mint="M" * 44, verdict=verdict,
                      findings=findings or [Finding("authorities", "PASS", "ok", {})],
                      unavailable=unavailable, price_usd=None, symbol=symbol,
                      duration_s=dur)


def test_verdict_view_avoid():
    v = verdict_view(result("AVOID"))
    assert v.label == "AVOID" and v.color == theme.VERDICT_COLORS["AVOID"]
    assert v.caption is None
    assert "TEST" in v.subtitle and "1.5" in v.subtitle


def test_verdict_view_clean_has_caption():
    v = verdict_view(result("NO_RED_FLAGS"))
    assert v.label == "NO RED FLAGS"
    assert v.caption == "no red flags ≠ safe"


def test_verdict_view_no_symbol_uses_short_mint():
    v = verdict_view(result("CAUTION", symbol=None))
    assert v.label == "CAUTION"
    assert "MMMM" in v.subtitle  # falls back to a truncated mint


def test_row_views_preserve_order_and_dim_info():
    findings = [Finding("authorities", "DISQUALIFIER", "bad", {}),
                Finding("vitals", "INFO", "age 3m", {})]
    rows = row_views(result(findings=findings))
    assert [r.severity for r in rows] == ["DISQUALIFIER", "INFO"]
    assert rows[0].color == theme.SEVERITY_COLORS["DISQUALIFIER"]
    assert rows[0].dim is False and rows[1].dim is True


def test_unavailable_footer():
    assert unavailable_footer(result(unavailable=0)) is None
    msg = unavailable_footer(result(unavailable=3))
    assert "3 of 6" in msg and "Settings" in msg
