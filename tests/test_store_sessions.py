import json

from arena.store import Store


def _store(tmp_path):
    return Store(tmp_path / "t.db")


def test_start_session_returns_an_id_and_persists_the_row(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [2.5, 4.0])
    assert isinstance(sid, int)
    rows = store.recent_watch_sessions()
    assert len(rows) == 1
    row = rows[0]
    assert row["mint"] == "MintA"
    assert row["started_ts"] == 1000
    assert row["sensitivity"] == "balanced"
    assert row["hazard_pct"] == 20.0
    assert json.loads(row["toggles"]) == [2.5, 4.0]
    assert row["entry_price"] is None
    assert row["resolved_ts"] is None
    store.close()


def test_two_sessions_get_distinct_ids(tmp_path):
    store = _store(tmp_path)
    a = store.start_watch_session("MintA", 1000, "early", 20.0, [])
    b = store.start_watch_session("MintB", 1001, "late", 50.0, [])
    assert a != b
    assert len(store.recent_watch_sessions()) == 2
    store.close()


def test_entry_price_is_set_once_and_read_back(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.set_session_entry_price(sid, 3.5e-8)
    assert store.recent_watch_sessions()[0]["entry_price"] == 3.5e-8
    store.close()


def test_signals_persist_with_all_fields(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.record_watch_signal(sid, 1010, "HEATING", "cascade alive",
                              0.71, 4.2, 0.0003)
    rows = store.watch_session_signals(sid)
    assert len(rows) == 1
    assert rows[0]["state"] == "HEATING"
    assert rows[0]["reason"] == "cascade alive"
    assert rows[0]["eta"] == 0.71
    assert rows[0]["lam"] == 4.2
    assert rows[0]["hold_drift"] == 0.0003
    store.close()


def test_signals_accept_null_numerics(tmp_path):
    """DISCONNECTED and WARMUP carry no numbers — the columns must be
    nullable, because a stale number is worse than no number."""
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.record_watch_signal(sid, 1010, "DISCONNECTED", "socket disconnected",
                              None, None, None)
    row = store.watch_session_signals(sid)[0]
    assert row["eta"] is None and row["lam"] is None
    assert row["hold_drift"] is None
    store.close()


def test_signals_return_in_timestamp_order(tmp_path):
    store = _store(tmp_path)
    sid = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    for ts, state in [(1030, "COOLING"), (1010, "WARMUP"), (1020, "HEATING")]:
        store.record_watch_signal(sid, ts, state, "r", None, None, None)
    assert [r["state"] for r in store.watch_session_signals(sid)] == [
        "WARMUP", "HEATING", "COOLING"]
    store.close()


def test_signals_are_scoped_to_their_session(tmp_path):
    store = _store(tmp_path)
    a = store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    b = store.start_watch_session("MintB", 1000, "balanced", 20.0, [])
    store.record_watch_signal(a, 1010, "HEATING", "cascade alive", None, None, None)
    assert len(store.watch_session_signals(a)) == 1
    assert store.watch_session_signals(b) == []
    store.close()


def test_recent_sessions_are_newest_first_and_respect_limit(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        store.start_watch_session(f"Mint{i}", 1000 + i, "balanced", 20.0, [])
    rows = store.recent_watch_sessions(limit=3)
    assert len(rows) == 3
    assert rows[0]["mint"] == "Mint4"
    store.close()


def test_existing_tables_still_work_after_schema_change(tmp_path):
    """The schema append must not disturb the pre-existing tables."""
    store = _store(tmp_path)
    store.set_manual_label("MintA", 1)
    assert store.manual_label("MintA") == 1
    assert store.label_counts()["labeled"] == 1
    store.close()
