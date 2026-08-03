"""The user's real database already has watch_sessions/watch_signals from an
earlier verification query on the pre-this-branch schema. CREATE TABLE IF
NOT EXISTS does not add columns to a table that already exists, so a bare
schema edit would leave the real database missing ended_ts/hazard_per_s/
eta_peak/lam_peak and every insert that sets them would fail at runtime,
while tests (which always start from a fresh temp database) would still
pass. This test builds a database with the OLD schema first, then opens it
with Store, and is the only test that would catch a broken migration.
"""

import sqlite3

from arena.store import Store

OLD_SCHEMA = """
CREATE TABLE watch_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    started_ts INTEGER NOT NULL,
    entry_price REAL,
    sensitivity TEXT NOT NULL,
    hazard_pct REAL NOT NULL,
    toggles TEXT NOT NULL,
    resolved_ts INTEGER
);
CREATE TABLE watch_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    eta REAL,
    lam REAL,
    hold_drift REAL
);
CREATE INDEX idx_watch_signals_session ON watch_signals(session_id, ts);
"""


def _old_db(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    # Seed a pre-existing row, the way the user's real session did, to prove
    # the migration is a genuine ALTER TABLE and not a drop-and-recreate
    # that would lose real data.
    conn.execute(
        "INSERT INTO watch_sessions (mint, started_ts, sensitivity, "
        "hazard_pct, toggles) VALUES ('RealMint', 500, 'balanced', 20.0, '[]')")
    conn.commit()
    conn.close()
    return path


def test_opening_an_old_schema_db_adds_the_new_columns_without_data_loss(tmp_path):
    path = _old_db(tmp_path)
    store = Store(path)

    cols = {r["name"] for r in
            store.conn.execute("PRAGMA table_info(watch_sessions)").fetchall()}
    assert "ended_ts" in cols

    sig_cols = {r["name"] for r in
                store.conn.execute("PRAGMA table_info(watch_signals)").fetchall()}
    assert {"hazard_per_s", "eta_peak", "lam_peak"} <= sig_cols

    # The pre-existing row survived the migration untouched.
    rows = store.recent_watch_sessions()
    assert len(rows) == 1
    assert rows[0]["mint"] == "RealMint"
    assert rows[0]["ended_ts"] is None
    store.close()


def test_inserts_using_the_new_columns_work_after_migrating_an_old_db(tmp_path):
    path = _old_db(tmp_path)
    store = Store(path)

    sid = store.start_watch_session("NewMint", 600, "balanced", 20.0, [])
    store.end_watch_session(sid, 700)
    store.record_watch_signal(sid, 650, "EXIT", "cascade decay", 0.3, 1.0,
                              0.0003, hazard_per_s=0.002, eta_peak=0.9,
                              lam_peak=5.0)

    row = store.recent_watch_sessions()[0]
    assert row["mint"] == "NewMint"
    assert row["ended_ts"] == 700

    sig = store.watch_session_signals(sid)[0]
    assert sig["hazard_per_s"] == 0.002
    assert sig["eta_peak"] == 0.9
    assert sig["lam_peak"] == 5.0
    store.close()


def test_migration_is_idempotent_across_repeated_opens(tmp_path):
    """Opening a database that already has the new columns must not raise
    (ALTER TABLE ADD COLUMN on an existing column errors), so the migration
    has to check PRAGMA table_info before each ALTER."""
    path = _old_db(tmp_path)
    Store(path).close()
    store = Store(path)   # second open, columns already migrated
    sid = store.start_watch_session("AnotherMint", 800, "balanced", 20.0, [])
    store.end_watch_session(sid, 900)
    assert store.recent_watch_sessions()[0]["ended_ts"] == 900
    store.close()
