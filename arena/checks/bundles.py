from collections import defaultdict

from arena.birth import Birth
from arena.models import DISQUALIFIER, INFO, PASS, WARNING, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient
from arena.thresholds import (BUNDLE_BUYERS_DISQUALIFIER, BUNDLE_BUYERS_WARNING,
                              LAUNCH_WINDOW_S)


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    if not birth.first_txs:
        if rpc.mode == "public":
            raise FeatureUnavailable("needs Helius key (Settings)")
        return Finding("bundles", INFO, "Launch history unavailable", {})
    cutoff = (birth.created_ts or 0) + LAUNCH_WINDOW_S
    buyers_by_slot: dict[int, set] = defaultdict(set)
    all_buyers: set = set()
    for tx in birth.first_txs:
        if (tx.get("timestamp") or 0) > cutoff:
            continue
        for t in tx.get("tokenTransfers") or []:
            if t.get("mint") == mint and t.get("toUserAccount"):
                buyers_by_slot[tx.get("slot", 0)].add(t["toUserAccount"])
                all_buyers.add(t["toUserAccount"])
    worst = max((len(b) for b in buyers_by_slot.values()), default=0)
    data = {"max_buyers_one_slot": worst, "launch_buyers": len(all_buyers)}
    msg = f"{worst} wallets bought in the same block at launch"
    if worst >= BUNDLE_BUYERS_DISQUALIFIER:
        return Finding("bundles", DISQUALIFIER, msg, data)
    if worst >= BUNDLE_BUYERS_WARNING:
        return Finding("bundles", WARNING, msg, data)
    return Finding("bundles", PASS,
                   f"No bundling — {len(all_buyers)} distinct launch buyers", data)
