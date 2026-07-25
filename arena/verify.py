import time

import httpx

from arena.prices import fetch_pair
from arena.store import Store
from arena.thresholds import DEAD_LIQUIDITY_USD, RUG_PRICE_RATIO, VERIFY_MIN_AGE_S


async def verify_outcomes(client: httpx.AsyncClient, store: Store,
                          now: int | None = None) -> list[tuple[str, str]]:
    now = now or int(time.time())
    labeled: list[tuple[str, str]] = []
    for row in store.unverified_scans(now - VERIFY_MIN_AGE_S):
        pair = await fetch_pair(client, row["mint"])
        if pair is None or (pair.liquidity_usd or 0) < DEAD_LIQUIDITY_USD:
            outcome = "DEAD"
        elif (row["price_usd_at_scan"] and pair.price_usd is not None
              and pair.price_usd <= RUG_PRICE_RATIO * row["price_usd_at_scan"]):
            outcome = "RUGGED"
        else:
            outcome = "ALIVE"
        store.record_outcome(row["mint"], outcome)
        labeled.append((row["mint"], outcome))
    return labeled
