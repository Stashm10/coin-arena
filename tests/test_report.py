from arena.models import Finding, ScanResult
from arena.report import flag_hit_rates
from arena.store import Store


def scan_with(store, mint, sev):
    store.save_scan(ScanResult(mint, "AVOID",
                    [Finding("dev_record", sev, "e", {})], 0, 1.0, "T", 1.0),
                    None, None, [])


def test_hit_rates(tmp_path):
    store = Store(tmp_path / "a.db")
    scan_with(store, "M1", "DISQUALIFIER"); store.record_outcome("M1", "RUGGED")
    scan_with(store, "M2", "DISQUALIFIER"); store.record_outcome("M2", "ALIVE")
    scan_with(store, "M3", "PASS");        store.record_outcome("M3", "ALIVE")
    rows = {r["check"]: r for r in flag_hit_rates(store)}
    dev = rows["dev_record"]
    assert dev["fired_total"] == 2 and dev["fired_bad"] == 1
    assert dev["quiet_total"] == 1 and dev["quiet_bad"] == 0
