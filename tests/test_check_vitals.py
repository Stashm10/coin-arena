import time

from arena.birth import Birth
from arena.checks import vitals
from arena.models import INFO
from arena.prices import PairInfo
from arena.rpc import RpcClient
from tests.helpers import make_client


async def test_vitals_full_mode():
    das = {"getTokenAccounts": {"token_accounts": [{"address": f"a{i}"} for i in range(42)]}}
    birth = Birth(created_ts=int(time.time()) - 221)
    pair = PairInfo(price_usd=0.01, liquidity_usd=12345.0, symbol="T")
    async with make_client(das) as c:
        f = await vitals.run(RpcClient(c, "k"), None, "M", birth, pair)
    assert f.severity == INFO
    assert f.data["holder_count"] == 42 and f.data["liquidity_usd"] == 12345.0
    assert 200 <= f.data["age_s"] <= 240


async def test_vitals_public_mode_degrades_gracefully():
    async with make_client() as c:  # DAS would raise FeatureUnavailable
        f = await vitals.run(RpcClient(c, None), None, "M", Birth(), None)
    assert f.severity == INFO and f.data["holder_count"] is None


async def test_vitals_truncated_birth_renders_lower_bound_age():
    birth = Birth(created_ts=int(time.time()) - 221, truncated=True)
    async with make_client() as c:
        f = await vitals.run(RpcClient(c, None), None, "M", birth, None)
    assert "history truncated" in f.evidence
    assert f.data["age_truncated"] is True
