import time

from arena.birth import Birth
from arena.models import INFO, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient, RpcError


def _fmt_age(age_s: int) -> str:
    if age_s < 3600:
        return f"{age_s // 60}m {age_s % 60}s"
    return f"{age_s // 3600}h {(age_s % 3600) // 60}m"


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    age_s = int(time.time()) - birth.created_ts if birth.created_ts else None
    holder_count = None
    try:
        das = await rpc.das("getTokenAccounts", {"mint": mint, "limit": 1000, "page": 1})
        holder_count = len(das.get("token_accounts") or [])
    except (FeatureUnavailable, RpcError):
        pass  # vitals degrades, never fails
    liq = pair.liquidity_usd if pair else None
    bits = []
    data = {"age_s": age_s, "holder_count": holder_count, "liquidity_usd": liq}
    if age_s is not None:
        if birth.truncated:
            bits.append(f"age ≥ {_fmt_age(age_s)} (history truncated)")
            data["age_truncated"] = True
        else:
            bits.append(f"age {_fmt_age(age_s)}")
    if holder_count is not None:
        bits.append(f"{'1000+' if holder_count >= 1000 else holder_count} holders")
    bits.append(f"liquidity ${liq:,.0f}" if liq is not None else "no DEX pair yet")
    return Finding("vitals", INFO, " · ".join(bits), data)
