from arena.birth import fetch_birth
from arena.rpc import RpcClient
from tests.helpers import make_client

SIGS = [  # newest-first, as Solana returns
    {"signature": "s3", "slot": 30, "blockTime": 300},
    {"signature": "s2", "slot": 20, "blockTime": 200},
    {"signature": "s1", "slot": 10, "blockTime": 100},
]
BY_SIG = {"__by_sig__": {
    "s1": {"signature": "s1", "feePayer": "Dev1", "slot": 10},
    "s2": {"signature": "s2", "feePayer": "Buyer", "slot": 20},
    "s3": {"signature": "s3", "feePayer": "Buyer2", "slot": 30},
}}


async def test_full_mode_birth():
    async with make_client({"getSignaturesForAddress": SIGS}, enhanced=BY_SIG) as c:
        b = await fetch_birth(RpcClient(c, "k"), "Mint1")
    assert b.creation_sig == "s1" and b.creator == "Dev1" and b.created_ts == 100
    assert [s["signature"] for s in b.first_sig_infos] == ["s1", "s2", "s3"]
    assert [t["signature"] for t in b.first_txs] == ["s1", "s2", "s3"]


async def test_public_mode_uses_get_transaction():
    rpc_methods = {
        "getSignaturesForAddress": SIGS,
        "getTransaction": {"transaction": {"message": {"accountKeys": [
            {"pubkey": "Dev1"}, {"pubkey": "Other"}]}}},
    }
    async with make_client(rpc_methods) as c:
        b = await fetch_birth(RpcClient(c, None), "Mint1")
    assert b.creator == "Dev1" and b.first_txs == []


async def test_rpc_failure_returns_empty_birth():
    async with make_client({"getSignaturesForAddress": 500}) as c:
        b = await fetch_birth(RpcClient(c, "k"), "Mint1")
    assert b.creation_sig is None and b.creator is None and b.first_txs == []


async def test_null_result_returns_empty_birth():
    async with make_client({"getSignaturesForAddress": lambda params: None}) as c:
        b = await fetch_birth(RpcClient(c, "k"), "Mint1")
    assert b.creation_sig is None and b.first_txs == []
