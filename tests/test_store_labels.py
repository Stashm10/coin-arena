import json

from arena.models import Finding, ScanResult
from arena.store import Store


def _scan(mint, verdict="AVOID", symbol="T"):
    return ScanResult(mint=mint, verdict=verdict,
                      findings=[Finding("holders", "WARNING", "e", {"top10_share": 0.4})],
                      unavailable=0, price_usd=1.0, symbol=symbol, duration_s=1.0)


def make(tmp_path):
    return Store(tmp_path / "a.db")


def test_set_get_clear_label(tmp_path):
    s = make(tmp_path)
    s.save_scan(_scan("M1"), None, None, [])
    assert s.manual_label("M1") is None
    s.set_manual_label("M1", 1)
    assert s.manual_label("M1") == 1
    s.set_manual_label("M1", 0)          # relabel
    assert s.manual_label("M1") == 0
    s.set_manual_label("M1", None)       # unsure clears it
    assert s.manual_label("M1") is None
    s.close()


def test_labeled_training_rows_uses_latest_scan(tmp_path):
    s = make(tmp_path)
    s.save_scan(_scan("M1", verdict="CAUTION"), None, None, [])
    s.save_scan(_scan("M1", verdict="AVOID"), None, None, [])   # newer scan of same mint
    s.set_manual_label("M1", 1)
    rows = s.labeled_training_rows()
    assert len(rows) == 1 and rows[0]["was_rug"] == 1
    parsed = json.loads(rows[0]["scan_json"])
    assert parsed[0]["check"] == "holders"
    s.close()


def test_label_counts(tmp_path):
    s = make(tmp_path)
    for m in ("M1", "M2", "M3"):
        s.save_scan(_scan(m), None, None, [])
    s.set_manual_label("M1", 1)
    s.set_manual_label("M2", 0)
    c = s.label_counts()
    assert c == {"total_scans": 3, "labeled": 2, "rugs": 1, "cleans": 1, "unlabeled": 1}
    s.close()


def test_scans_for_history_one_row_per_mint_with_label(tmp_path):
    s = make(tmp_path)
    s.save_scan(_scan("M1", symbol="AAA"), None, None, [])
    s.save_scan(_scan("M1", symbol="AAA"), None, None, [])  # dup mint
    s.save_scan(_scan("M2", symbol="BBB"), None, None, [])
    s.set_manual_label("M1", 1)
    rows = s.scans_for_history()
    mints = [r["mint"] for r in rows]
    assert mints.count("M1") == 1 and "M2" in mints
    m1 = next(r for r in rows if r["mint"] == "M1")
    assert m1["was_rug"] == 1 and m1["symbol"] == "AAA"
    m2 = next(r for r in rows if r["mint"] == "M2")
    assert m2["was_rug"] is None
    s.close()
