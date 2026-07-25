from arena.birth import Birth
from arena.models import DISQUALIFIER, INFO, PASS, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient
from arena.thresholds import FUNDING_MAX_SIGS


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    if not birth.creator:
        return Finding("funding", INFO, "Creator wallet unknown", {"funder": None})
    sigs = await rpc.rpc("getSignaturesForAddress",
                         [birth.creator, {"limit": FUNDING_MAX_SIGS}])
    if len(sigs) >= FUNDING_MAX_SIGS:
        return Finding("funding", INFO,
                       "Creator wallet too active to trace funding cheaply",
                       {"funder": None})
    if not sigs:
        return Finding("funding", INFO, "Creator wallet has no history",
                       {"funder": None})
    if rpc.mode == "public":
        raise FeatureUnavailable("needs Helius key (Settings)")
    oldest = sigs[-1]["signature"]
    txs = await rpc.enhanced_batch([oldest])
    funder = None
    for t in (txs[0].get("nativeTransfers") or []) if txs else []:
        if t.get("toUserAccount") == birth.creator and t.get("fromUserAccount"):
            funder = t["fromUserAccount"]
            break
    if not funder:
        return Finding("funding", INFO, "Could not identify funder",
                       {"funder": None})
    rugs = store.funder_rugged_count(funder)
    data = {"funder": funder}
    if rugs >= 1:
        return Finding("funding", DISQUALIFIER,
                       f"Funded by wallet that funded {rugs} rugged coin(s)", data)
    return Finding("funding", PASS,
                   "Funder has no rug history in your database", data)
