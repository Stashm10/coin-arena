"""Live Jito landed-tip percentiles — free, no API key.

Scope note: Coin Arena is advisory. The user types a number into their own
terminal, whose fee logic sits between them and the block. This reports what is
currently landing; it cannot promise inclusion.
"""

from dataclasses import dataclass

import httpx

TIP_FLOOR_URL = "https://bundles.jito.wtf/api/v1/bundles/tip_floor"


class TipLookupError(Exception):
    pass


@dataclass
class TipFloor:
    p25: float
    p50: float
    p75: float
    p95: float
    p99: float


async def fetch_tips(client: httpx.AsyncClient) -> TipFloor:
    try:
        resp = await client.get(TIP_FLOOR_URL, timeout=10)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        raise TipLookupError(str(exc)) from None
    if not isinstance(body, list) or not body:
        raise TipLookupError("empty tip_floor response")
    row = body[0]
    try:
        return TipFloor(
            p25=float(row["landed_tips_25th_percentile"]),
            p50=float(row["landed_tips_50th_percentile"]),
            p75=float(row["landed_tips_75th_percentile"]),
            p95=float(row["landed_tips_95th_percentile"]),
            p99=float(row["landed_tips_99th_percentile"]))
    except (KeyError, TypeError, ValueError):
        raise TipLookupError("malformed tip_floor response") from None


def recommend(tips: TipFloor, aggressiveness: str) -> float:
    return {"low": tips.p50, "normal": tips.p75,
            "high": tips.p95}.get(aggressiveness, tips.p75)
