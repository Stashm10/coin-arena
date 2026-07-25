import asyncio
import re
import time

import httpx

from arena.birth import fetch_birth
from arena.checks import run_all_checks
from arena.models import INFO, ScanResult
from arena.prices import fetch_pair
from arena.rpc import RpcClient
from arena.scoring import verdict
from arena.settings import Settings
from arena.store import Store

MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


async def check_mint(mint: str, settings: Settings, store: Store,
                     client: httpx.AsyncClient) -> ScanResult:
    if not MINT_RE.match(mint):
        raise ValueError("not a valid Solana mint address")
    start = time.monotonic()
    rpc = RpcClient(client, settings.helius_key)
    birth, pair = await asyncio.gather(fetch_birth(rpc, mint),
                                       fetch_pair(client, mint))
    findings = await run_all_checks(rpc, store, mint, birth, pair)
    by_check = {f.check: f for f in findings}

    owners = by_check["holders"].data.get("owners", [])
    smart = store.survivor_wallet_count(owners) if owners else 0
    by_check["vitals"].data["smart_money"] = smart
    if smart:
        by_check["vitals"].evidence += f" · {smart} top holders have winning history"

    unavailable = sum(1 for f in findings if f.severity == INFO and
                      ("unavailable" in f.evidence or "needs Helius key" in f.evidence))
    result = ScanResult(
        mint=mint, verdict=verdict(findings), findings=findings,
        unavailable=unavailable,
        price_usd=pair.price_usd if pair else None,
        symbol=pair.symbol if pair else None,
        duration_s=round(time.monotonic() - start, 2))
    store.save_scan(result, creator=birth.creator,
                    funder=by_check["funding"].data.get("funder"),
                    top_holders=owners)
    return result
