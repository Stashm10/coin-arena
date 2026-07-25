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

    def close(self) -> None:
        self.conn.close()
