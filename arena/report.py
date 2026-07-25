import json

from arena.models import CHECK_NAMES, DISQUALIFIER, WARNING
from arena.store import Store

BAD = ("RUGGED", "DEAD")


def flag_hit_rates(store: Store) -> list[dict]:
    stats = {c: {"check": c, "fired_bad": 0, "fired_total": 0,
                 "quiet_bad": 0, "quiet_total": 0} for c in CHECK_NAMES}
    for row in store.scans_with_outcomes():
        bad = row["outcome"] in BAD
        by_check = {f["check"]: f for f in json.loads(row["scan_json"])}
        for name in CHECK_NAMES:
            f = by_check.get(name)
            if f is None:
                continue
            fired = f["severity"] in (WARNING, DISQUALIFIER)
            bucket = "fired" if fired else "quiet"
            stats[name][f"{bucket}_total"] += 1
            if bad:
                stats[name][f"{bucket}_bad"] += 1
    return [s for s in stats.values() if s["fired_total"] or s["quiet_total"]]
