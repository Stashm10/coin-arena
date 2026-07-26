"""Shared feature-extraction contract. Both arena.train (offline) and the
live scanner (arena.engine) call extract_features, so the model can never be
fed a different feature layout than it was trained on.

Input is the parsed scan_json shape: a list of dicts, each
{"check", "severity", "evidence", "data"}. Missing findings or keys impute to
0.0 (a known simplification for scans where a check was unavailable)."""

from arena.models import DISQUALIFIER

FEATURE_NAMES = [
    "mint_authority",       # authorities.data.mint_authority (active -> 1)
    "freeze_authority",     # authorities.data.freeze_authority (active -> 1)
    "top10_share",          # holders.data.top10_share (0..1)
    "max_single",           # holders.data.max_single (0..1)
    "max_buyers_one_slot",  # bundles.data.max_buyers_one_slot
    "launch_buyers",        # bundles.data.launch_buyers
    "prior_launches",       # dev_record.data.prior_launches
    "funder_rugged",        # funding severity == DISQUALIFIER -> 1
    "age_s",                # vitals.data.age_s
    "holder_count",         # vitals.data.holder_count
    "liquidity_usd",        # vitals.data.liquidity_usd
]


def extract_features(findings: list[dict]) -> list[float]:
    by_check: dict[str, dict] = {}
    for f in findings or []:
        if isinstance(f, dict) and isinstance(f.get("check"), str):
            by_check[f["check"]] = f

    def data(check: str) -> dict:
        d = (by_check.get(check) or {}).get("data")
        return d if isinstance(d, dict) else {}

    def num(check: str, key: str) -> float:
        v = data(check).get(key)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    auth = data("authorities")
    funding_sev = (by_check.get("funding") or {}).get("severity")
    return [
        1.0 if auth.get("mint_authority") else 0.0,
        1.0 if auth.get("freeze_authority") else 0.0,
        num("holders", "top10_share"),
        num("holders", "max_single"),
        num("bundles", "max_buyers_one_slot"),
        num("bundles", "launch_buyers"),
        num("dev_record", "prior_launches"),
        1.0 if funding_sev == DISQUALIFIER else 0.0,
        num("vitals", "age_s"),
        num("vitals", "holder_count"),
        num("vitals", "liquidity_usd"),
    ]
