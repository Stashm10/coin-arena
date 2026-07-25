import pytest

from arena.rpc import FeatureUnavailable, RpcClient, RpcError, redact
from tests.helpers import make_client


def test_redact():
    assert redact("url 'https://x/?api-key=abc-123' failed") == \
        "url 'https://x/?api-key=***' failed"
    assert redact("clean") == "clean"


async def test_rpc_result_roundtrip():
    async with make_client({"getSlot": 123}) as c:
        assert await RpcClient(c, "k").rpc("getSlot", []) == 123


async def test_rpc_error_raises_rpcerror_redacted():
    async with make_client({"getSlot": 500}) as c:
        with pytest.raises(RpcError) as ei:
            await RpcClient(c, "secret-key").rpc("getSlot", [])
        assert "secret-key" not in str(ei.value)


async def test_public_mode_blocks_enhanced_and_das():
    async with make_client() as c:
        rpc = RpcClient(c, None)
        assert rpc.mode == "public"
        with pytest.raises(FeatureUnavailable):
            await rpc.enhanced_txs("SomeAddr")
        with pytest.raises(FeatureUnavailable):
            await rpc.das("getTokenAccounts", {})


async def test_enhanced_txs_full_mode():
    txs = [{"signature": "s2"}, {"signature": "s1"}]
    async with make_client(enhanced={"Addr1": txs}) as c:
        got = await RpcClient(c, "k").enhanced_txs("Addr1", limit=1)
        assert got == [{"signature": "s2"}]


async def test_enhanced_batch():
    async with make_client(enhanced={"__by_sig__": {"s1": {"signature": "s1"}}}) as c:
        got = await RpcClient(c, "k").enhanced_batch(["s1"])
        assert got == [{"signature": "s1"}]
