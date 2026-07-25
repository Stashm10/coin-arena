import json

from arena.models import Finding, ScanResult
from arena.store import Store


def scan(mint="M1", verdict="AVOID", price=0.5):
    return ScanResult(mint=mint, verdict=verdict,
                      findings=[Finding("authorities", "DISQUALIFIER", "e", {"x": 1})],
                      unavailable=0, price_usd=price, symbol="T", duration_s=1.0)


def make(tmp_path):
    return Store(tmp_path / "a.db")


def test_save_and_unverified(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan(), creator="Dev1", funder="Fund1", top_holders=["H1", "H2"])
    rows = s.unverified_scans(older_than_ts=2**62)
    assert len(rows) == 1
    assert rows[0]["mint"] == "M1" and rows[0]["price_usd_at_scan"] == 0.5
    s.close()


def test_record_outcome_bumps_wallets(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), "Dev1", "Fund1", ["H1"])
    s.save_scan(scan("M2"), "Dev1", "Fund1", ["H1"])
    s.record_outcome("M1", "RUGGED")
    s.record_outcome("M2", "ALIVE")
    assert s.funder_rugged_count("Fund1") == 1
    assert s.survivor_wallet_count(["H1", "Nobody"]) == 1
    assert s.unverified_scans(2**62) == []
    s.close()


def test_dead_bumps_neither(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), "Dev1", "Fund1", ["H1"])
    s.record_outcome("M1", "DEAD")
    assert s.funder_rugged_count("Fund1") == 0
    assert s.survivor_wallet_count(["H1"]) == 0
    s.close()


def test_scan_json_roundtrip_and_report_rows(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), None, None, [])
    s.record_outcome("M1", "RUGGED")
    rows = s.scans_with_outcomes()
    assert rows[0]["outcome"] == "RUGGED"
    parsed = json.loads(rows[0]["scan_json"])
    assert parsed[0]["check"] == "authorities" and parsed[0]["data"] == {"x": 1}
    s.close()


def test_duplicate_scan_wallets_ignored(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), "Dev1", "Dev1", ["Dev1"])   # same addr, 3 roles: ok
    s.save_scan(scan("M1"), "Dev1", None, ["Dev1"])     # rescan: no unique violation
    s.close()
