from dataclasses import dataclass

from arena.gui import theme
from arena.models import ScanResult

_LABELS = {"AVOID": "AVOID", "CAUTION": "CAUTION", "NO_RED_FLAGS": "NO RED FLAGS"}


@dataclass
class VerdictView:
    label: str
    color: str
    caption: str | None
    subtitle: str


@dataclass
class RowView:
    severity: str
    color: str
    evidence: str
    dim: bool


def verdict_view(result: ScanResult) -> VerdictView:
    name = result.symbol or (result.mint[:8] + "…")
    return VerdictView(
        label=_LABELS[result.verdict],
        color=theme.VERDICT_COLORS[result.verdict],
        caption="no red flags ≠ safe" if result.verdict == "NO_RED_FLAGS" else None,
        subtitle=f"{name} · scanned in {result.duration_s}s",
    )


def row_views(result: ScanResult) -> list[RowView]:
    return [RowView(severity=f.severity,
                    color=theme.SEVERITY_COLORS.get(f.severity, theme.MUTED),
                    evidence=f.evidence, dim=(f.severity == "INFO"))
            for f in result.findings]


def unavailable_footer(result: ScanResult) -> str | None:
    if result.unavailable <= 0:
        return None
    return (f"{result.unavailable} of 6 checks unavailable — "
            "add your Helius key in Settings")
