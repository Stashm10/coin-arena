import time

from arena.models import Finding, ScanResult
from arena.store import Store
from arena.verify import verify_outcomes
from tests.helpers import make_client


def seed(store, mint, price):
    store.save_scan(ScanResult(mint, "NO_RED_FLAGS",
                    [Finding("authorities", "PASS", "e", {})], 0, price, "T", 1.0),
                    None, None, [])
    store.conn.execute("UPDATE scans SET ts = ? WHERE mint = ?",
                       (int(time.time()) - 100000, mint))
    store.conn.commit()


async def test_labels_dead_rugged_alive(tmp_path):
    store = Store(tmp_path / "a.db")
    seed(store, "MintDead", 1.0)
    seed(store, "MintRug", 1.0)
    seed(store, "MintOk", 1.0)
    ds = {
        "MintDead": {"pairs": None},
        "MintRug": {"pairs": [{"priceUsd": "0.05", "liquidity": {"usd": 5000},
                               "baseToken": {"symbol": "R"}}]},
        "MintOk": {"pairs": [{"priceUsd": "2.0", "liquidity": {"usd": 9000},
                              "baseToken": {"symbol": "O"}}]},
    }
    async with make_client(dexscreener=ds) as c:
        labeled = dict(await verify_outcomes(c, store))
    assert labeled == {"MintDead": "DEAD", "MintRug": "RUGGED", "MintOk": "ALIVE"}
    assert store.unverified_scans(2**62) == []


async def test_fresh_scans_not_verified_yet(tmp_path):
    store = Store(tmp_path / "a.db")
    store.save_scan(ScanResult("MintNew", "NO_RED_FLAGS", [], 0, 1.0, "T", 1.0),
                    None, None, [])
    async with make_client() as c:
        assert await verify_outcomes(c, store) == []
