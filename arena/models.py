from dataclasses import dataclass, field

DISQUALIFIER = "DISQUALIFIER"
WARNING = "WARNING"
PASS = "PASS"
INFO = "INFO"

AVOID = "AVOID"
CAUTION = "CAUTION"
NO_RED_FLAGS = "NO_RED_FLAGS"

CHECK_NAMES = ["authorities", "holders", "bundles", "dev_record", "funding", "vitals"]


@dataclass
class Finding:
    check: str
    severity: str
    evidence: str
    data: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    mint: str
    verdict: str
    findings: list[Finding]
    unavailable: int
    price_usd: float | None
    symbol: str | None
    duration_s: float
    rug_probability: float | None = None
