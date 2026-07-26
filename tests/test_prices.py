import httpx
import pytest

from arena.prices import PairLookupError, fetch_pair
from tests.helpers import make_client

DS = {"MintA": {"pairs": [
    {"priceUsd": "0.5", "liquidity": {"usd": 100}, "baseToken": {"symbol": "LOW"}},
    {"priceUsd": "0.9", "liquidity": {"usd": 9000}, "baseToken": {"symbol": "FISTY"}},
]}}


async def test_picks_highest_liquidity_pair():
    async with make_client(dexscreener=DS) as c:
        p = await fetch_pair(c, "MintA")
    assert p.price_usd == 0.9 and p.liquidity_usd == 9000 and p.symbol == "FISTY"


async def test_no_pairs_returns_none():
    async with make_client(dexscreener={"MintB": {"pairs": None}}) as c:
        assert await fetch_pair(c, "MintB") is None


async def test_malformed_pair_raises_pair_lookup_error():
    # A malformed entry in an otherwise-successful response means we
    # couldn't parse it, not that we confirmed there are no pairs.
    async with make_client(dexscreener={"MintC": {"pairs": [None]}}) as c:
        with pytest.raises(PairLookupError):
            await fetch_pair(c, "MintC")


async def test_transport_failure_raises_pair_lookup_error():
    async with make_client(dexscreener={"MintD": 500}) as c:
        with pytest.raises(PairLookupError):
            await fetch_pair(c, "MintD")


async def test_non_dict_body_raises_pairlookuperror():
    # Valid JSON, but not a dict (e.g. DexScreener returns a bare array) —
    # .get("pairs") on it must not leak a raw AttributeError past callers'
    # `except PairLookupError`.
    def handler(request):
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(PairLookupError):
            await fetch_pair(c, "MintA")
