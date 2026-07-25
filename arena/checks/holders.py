from arena.birth import Birth
from arena.models import DISQUALIFIER, PASS, WARNING, Finding
from arena.prices import PairInfo
from arena.rpc import RpcClient
from arena.thresholds import (SINGLE_HOLDER_WARNING, TOP10_SHARE_DISQUALIFIER,
                              TOP10_SHARE_WARNING)

SYSTEM_PROGRAM = "11111111111111111111111111111111"


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    largest = await rpc.rpc("getTokenLargestAccounts", [mint])
    supply = await rpc.rpc("getTokenSupply", [mint])
    total = (supply["value"] or {}).get("uiAmount") or 0
    entries = [(v["address"], v.get("uiAmount") or 0) for v in largest["value"]]
    if not entries or not total:
        return Finding("holders", PASS, "No holder data yet",
                       {"top10_share": 0.0, "max_single": 0.0, "owners": []})

    token_accounts = [a for a, _ in entries]
    parsed = await rpc.rpc("getMultipleAccounts",
                           [token_accounts, {"encoding": "jsonParsed"}])
    owners_by_ta = {}
    for (ta, _), acc in zip(entries, parsed["value"]):
        if acc:
            owners_by_ta[ta] = acc["data"]["parsed"]["info"]["owner"]

    unique_owners = list(dict.fromkeys(owners_by_ta.values()))
    owner_accs = await rpc.rpc("getMultipleAccounts",
                               [unique_owners, {"encoding": "base64"}])
    human = {o for o, acc in zip(unique_owners, owner_accs["value"])
             if acc is not None and acc.get("owner") == SYSTEM_PROGRAM}

    amounts: dict[str, float] = {}
    for ta, amt in entries:
        o = owners_by_ta.get(ta)
        if o in human:
            amounts[o] = amounts.get(o, 0) + amt
    ranked = sorted(amounts.items(), key=lambda kv: kv[1], reverse=True)
    shares = [amt / total for _, amt in ranked]
    top10 = round(sum(shares[:10]), 4)
    max_single = round(shares[0], 4) if shares else 0.0
    data = {"top10_share": top10, "max_single": max_single,
            "owners": [o for o, _ in ranked[:20]]}
    pct = f"{top10:.0%}"
    if top10 > TOP10_SHARE_DISQUALIFIER:
        return Finding("holders", DISQUALIFIER,
                       f"Top 10 humans hold {pct} of supply", data)
    if top10 > TOP10_SHARE_WARNING:
        return Finding("holders", WARNING,
                       f"Top 10 humans hold {pct} of supply", data)
    if max_single > SINGLE_HOLDER_WARNING:
        return Finding("holders", WARNING,
                       f"One wallet holds {max_single:.0%} of supply", data)
    return Finding("holders", PASS,
                   f"Supply dispersed — top 10 humans hold {pct}", data)
