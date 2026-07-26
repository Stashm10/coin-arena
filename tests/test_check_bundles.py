import pytest

from arena.birth import Birth
from arena.checks import bundles
from arena.models import DISQUALIFIER, INFO, PASS, WARNING
from arena.rpc import FeatureUnavailable, RpcClient
from tests.helpers import make_client

MINT = "MintX"


def tx(sig, slot, ts, buyers):
    return {"signature": sig, "slot": slot, "timestamp": ts,
            "tokenTransfers": [
                {"mint": MINT, "toUserAccount": b, "fromUserAccount": "pool"}
                for b in buyers]}


def birth_with(txs):
    return Birth(creation_sig="s0", creator="Dev", created_ts=100,
                 first_sig_infos=[], first_txs=txs)


async def test_eight_buyers_one_slot_disqualifies():
    txs = [tx(f"s{i}", 10, 101, [f"B{i}"]) for i in range(8)]
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with(txs), None)
    assert f.severity == DISQUALIFIER and f.data["max_buyers_one_slot"] == 8


async def test_four_buyers_one_slot_warns():
    txs = [tx(f"s{i}", 10, 101, [f"B{i}"]) for i in range(4)]
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with(txs), None)
    assert f.severity == WARNING


async def test_spread_buys_pass_and_window_respected():
    txs = [tx(f"s{i}", 10 + i, 101, [f"B{i}"]) for i in range(3)]
    txs += [tx("late", 99, 500, ["Late1", "Late2", "Late3", "Late4", "Late5"])]
    async with make_client() as c:  # late tx outside 60s window: ignored
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with(txs), None)
    assert f.severity == PASS


async def test_public_mode_raises_feature_unavailable():
    async with make_client() as c:
        with pytest.raises(FeatureUnavailable):
            await bundles.run(RpcClient(c, None), None, MINT, birth_with([]), None)


async def test_full_mode_no_history_is_info():
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with([]), None)
    assert f.severity == INFO


async def test_truncated_history_is_info_too_established():
    truncated_birth = Birth(creation_sig="s0", creator="Dev", created_ts=100,
                            first_sig_infos=[], first_txs=[], truncated=True)
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, truncated_birth, None)
    assert f.severity == INFO
    assert "too established" in f.evidence
    assert f.data["truncated"] is True
