from dataclasses import dataclass

import httpx

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


@dataclass
class PairInfo:
    price_usd: float | None
    liquidity_usd: float | None
    symbol: str | None


async def fetch_pair(client: httpx.AsyncClient, mint: str) -> PairInfo | None:
    """Best-liquidity pair from DexScreener. None on any failure — a missing
    price must never block or crash a scan."""
    try:
        resp = await client.get(DEXSCREENER_URL.format(mint=mint), timeout=10)
        resp.raise_for_status()
        pairs = resp.json().get("pairs") or []
        if not pairs:
            return None
        best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        liq = (best.get("liquidity") or {}).get("usd")
        return PairInfo(
            price_usd=float(best["priceUsd"]) if best.get("priceUsd") else None,
            liquidity_usd=float(liq) if liq is not None else None,
            symbol=(best.get("baseToken") or {}).get("symbol"),
        )
    except Exception:
        return None
