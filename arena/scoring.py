from arena.models import AVOID, CAUTION, DISQUALIFIER, NO_RED_FLAGS, WARNING, Finding


def verdict(findings: list[Finding]) -> str:
    severities = [f.severity for f in findings]
    if DISQUALIFIER in severities:
        return AVOID
    if severities.count(WARNING) >= 2:
        return CAUTION
    return NO_RED_FLAGS
