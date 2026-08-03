import json
import time
from dataclasses import asdict
from pathlib import Path

import sqlite3

from arena.paths import data_dir
from arena.models import ScanResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    mint TEXT NOT NULL,
    symbol TEXT,
    verdict TEXT NOT NULL,
    price_usd_at_scan REAL,
    scan_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coin_outcomes (
    mint TEXT PRIMARY KEY,
    scanned_ts INTEGER,
    verified_ts INTEGER,
    outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wallets (
    address TEXT PRIMARY KEY,
    times_seen INTEGER DEFAULT 0,
    times_in_rugged INTEGER DEFAULT 0,
    times_in_survivors INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS scan_wallets (
    mint TEXT NOT NULL,
    address TEXT NOT NULL,
    role TEXT NOT NULL,
    UNIQUE(mint, address, role)
);
CREATE TABLE IF NOT EXISTS manual_labels (
    mint TEXT PRIMARY KEY,
    was_rug INTEGER NOT NULL,
    ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS funding_edges (
    child TEXT PRIMARY KEY,
    parent TEXT,
    is_root INTEGER NOT NULL DEFAULT 0,
    resolved_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    started_ts INTEGER NOT NULL,
    entry_price REAL,
    sensitivity TEXT NOT NULL,
    hazard_pct REAL NOT NULL,
    toggles TEXT NOT NULL,
    resolved_ts INTEGER
);
CREATE TABLE IF NOT EXISTS watch_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    eta REAL,
    lam REAL,
    hold_drift REAL
);
CREATE INDEX IF NOT EXISTS idx_watch_signals_session
    ON watch_signals(session_id, ts);
"""


class Store:
    def __init__(self, path: str | Path | None = None):
        self.conn = sqlite3.connect(path or data_dir() / "arena.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def save_scan(self, result: ScanResult, creator: str | None,
                  funder: str | None, top_holders: list[str]) -> None:
        self.conn.execute(
            "INSERT INTO scans (ts, mint, symbol, verdict, price_usd_at_scan, scan_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (int(time.time()), result.mint, result.symbol, result.verdict,
             result.price_usd, json.dumps([asdict(f) for f in result.findings])))
        links = [(result.mint, creator, "creator"), (result.mint, funder, "funder")]
        links += [(result.mint, h, "top_holder") for h in top_holders]
        for mint, addr, role in links:
            if not addr:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO scan_wallets (mint, address, role) VALUES (?,?,?)",
                (mint, addr, role))
            self.conn.execute(
                "INSERT INTO wallets (address, times_seen) VALUES (?, 1) "
                "ON CONFLICT(address) DO UPDATE SET times_seen = times_seen + 1",
                (addr,))
        self.conn.commit()

    def unverified_scans(self, older_than_ts: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.mint, MIN(s.ts) AS ts, s.price_usd_at_scan FROM scans s "
            "LEFT JOIN coin_outcomes o ON o.mint = s.mint "
            "WHERE o.mint IS NULL GROUP BY s.mint HAVING MIN(s.ts) <= ?",
            (older_than_ts,)).fetchall()
        return [dict(r) for r in rows]

    def record_outcome(self, mint: str, outcome: str) -> None:
        row = self.conn.execute("SELECT MIN(ts) AS t FROM scans WHERE mint = ?",
                                (mint,)).fetchone()
        self.conn.execute(
            "INSERT INTO coin_outcomes (mint, scanned_ts, verified_ts, outcome) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(mint) DO UPDATE SET "
            "outcome = excluded.outcome, verified_ts = excluded.verified_ts",
            (mint, row["t"], int(time.time()), outcome))
        col = {"RUGGED": "times_in_rugged", "ALIVE": "times_in_survivors"}.get(outcome)
        if col:
            self.conn.execute(
                f"UPDATE wallets SET {col} = {col} + 1 WHERE address IN "
                "(SELECT address FROM scan_wallets WHERE mint = ?)", (mint,))
        self.conn.commit()

    def funder_rugged_count(self, funder: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT sw.mint) AS n FROM scan_wallets sw "
            "JOIN coin_outcomes o ON o.mint = sw.mint "
            "WHERE sw.address = ? AND sw.role = 'funder' AND o.outcome = 'RUGGED'",
            (funder,)).fetchone()
        return row["n"]

    def survivor_wallet_count(self, addresses: list[str]) -> int:
        if not addresses:
            return 0
        q = ",".join("?" * len(addresses))
        row = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM wallets WHERE address IN ({q}) "
            "AND times_in_survivors >= 1", addresses).fetchone()
        return row["n"]

    def scans_with_outcomes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.scan_json, o.outcome FROM scans s "
            "JOIN coin_outcomes o ON o.mint = s.mint").fetchall()
        return [dict(r) for r in rows]

    def recent_scans(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.ts, s.mint, s.symbol, s.verdict, o.outcome FROM scans s "
            "LEFT JOIN coin_outcomes o ON o.mint = s.mint "
            "ORDER BY s.id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def set_manual_label(self, mint: str, was_rug: int | None) -> None:
        if was_rug is None:
            self.conn.execute("DELETE FROM manual_labels WHERE mint = ?", (mint,))
        else:
            self.conn.execute(
                "INSERT INTO manual_labels (mint, was_rug, ts) VALUES (?, ?, ?) "
                "ON CONFLICT(mint) DO UPDATE SET was_rug = excluded.was_rug, "
                "ts = excluded.ts",
                (mint, int(was_rug), int(time.time())))
        self.conn.commit()

    def manual_label(self, mint: str) -> int | None:
        row = self.conn.execute(
            "SELECT was_rug FROM manual_labels WHERE mint = ?", (mint,)).fetchone()
        return row["was_rug"] if row else None

    def labeled_training_rows(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.scan_json AS scan_json, m.was_rug AS was_rug "
            "FROM manual_labels m JOIN scans s ON s.id = "
            "(SELECT id FROM scans WHERE mint = m.mint ORDER BY id DESC LIMIT 1)"
        ).fetchall()
        return [dict(r) for r in rows]

    def label_counts(self) -> dict:
        total = self.conn.execute(
            "SELECT COUNT(DISTINCT mint) AS n FROM scans").fetchone()["n"]
        labeled = self.conn.execute(
            "SELECT COUNT(*) AS n FROM manual_labels").fetchone()["n"]
        rugs = self.conn.execute(
            "SELECT COUNT(*) AS n FROM manual_labels WHERE was_rug = 1").fetchone()["n"]
        return {"total_scans": total, "labeled": labeled, "rugs": rugs,
                "cleans": labeled - rugs, "unlabeled": total - labeled}

    def scans_for_history(self, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.mint, s.symbol, s.ts, s.verdict, m.was_rug FROM scans s "
            "JOIN (SELECT mint, MAX(id) AS mid FROM scans GROUP BY mint) latest "
            "ON latest.mid = s.id "
            "LEFT JOIN manual_labels m ON m.mint = s.mint "
            "ORDER BY s.ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def cached_edge(self, child: str) -> tuple[str | None, bool] | None:
        row = self.conn.execute(
            "SELECT parent, is_root FROM funding_edges WHERE child = ?",
            (child,)).fetchone()
        return (row["parent"], bool(row["is_root"])) if row else None

    def save_edge(self, child: str, parent: str | None, is_root: bool) -> None:
        self.conn.execute(
            "INSERT INTO funding_edges (child, parent, is_root, resolved_ts) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(child) DO UPDATE SET "
            "parent = excluded.parent, is_root = excluded.is_root, "
            "resolved_ts = excluded.resolved_ts",
            (child, parent, int(is_root), int(time.time())))
        self.conn.commit()

    def start_watch_session(self, mint: str, started_ts: int, sensitivity: str,
                           hazard_pct: float, toggles: list[float]) -> int:
        cur = self.conn.execute(
            "INSERT INTO watch_sessions (mint, started_ts, sensitivity, "
            "hazard_pct, toggles) VALUES (?, ?, ?, ?, ?)",
            (mint, started_ts, sensitivity, hazard_pct, json.dumps(toggles)))
        self.conn.commit()
        return cur.lastrowid

    def set_session_entry_price(self, session_id: int, price: float) -> None:
        self.conn.execute(
            "UPDATE watch_sessions SET entry_price = ? WHERE id = ?",
            (price, session_id))
        self.conn.commit()

    def record_watch_signal(self, session_id: int, ts: int, state: str,
                            reason: str, eta: float | None, lam: float | None,
                            hold_drift: float | None) -> None:
        self.conn.execute(
            "INSERT INTO watch_signals (session_id, ts, state, reason, eta, "
            "lam, hold_drift) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, ts, state, reason, eta, lam, hold_drift))
        self.conn.commit()

    def watch_session_signals(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, state, reason, eta, lam, hold_drift FROM watch_signals "
            "WHERE session_id = ? ORDER BY ts, id", (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def recent_watch_sessions(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, mint, started_ts, entry_price, sensitivity, hazard_pct,"
            " toggles, resolved_ts FROM watch_sessions "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
