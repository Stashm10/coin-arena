from dataclasses import dataclass

import httpx

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


class PairLookupError(Exception):
    """Raised when DexScreener could not be reached or its response could not
    be parsed — distinct from a successful response confirming no pairs
    exist. Callers must not treat this the same as "no pairs" (None)."""


@dataclass
class PairInfo:
    price_usd: float | None
    liquidity_usd: float | None
    symbol: str | None


async def fetch_pair(client: httpx.AsyncClient, mint: str) -> PairInfo | None:
    """Best-liquidity pair from DexScreener.

    Returns None when DexScreener successfully confirms there are no pairs.
    Raises PairLookupError when the lookup itself failed (transport, HTTP,
    or parse error) — a transport failure must never be confused with a
    confirmed "no pairs" result, or an outage would mislabel every pending
    coin as DEAD.
    """
    try:
        resp = await client.get(DEXSCREENER_URL.format(mint=mint), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        pairs = data.get("pairs") or []
    except Exception as exc:
        raise PairLookupError(str(exc)) from None

    if not pairs:
        return None

    try:
        best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        liq = (best.get("liquidity") or {}).get("usd")
        return PairInfo(
            price_usd=float(best["priceUsd"]) if best.get("priceUsd") else None,
            liquidity_usd=float(liq) if liq is not None else None,
            symbol=(best.get("baseToken") or {}).get("symbol"),
        )
    except Exception as exc:
        raise PairLookupError(str(exc)) from None
