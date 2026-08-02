from arena.checks.entropy import funding_entropy
from arena.funding_graph import (CEX_ADDRESSES, funder_of, is_root_like,
                                 resolve_roots)
from arena.rpc import RpcClient
from arena.store import Store
from arena.thresholds import FUNDING_PAGE_SIZE, FUNDING_ROOT_TX_COUNT
from tests.helpers import make_client


def _funding_tx(sender, receiver):
    return {"signature": f"{sender}->{receiver}", "timestamp": 100,
            "nativeTransfers": [{"fromUserAccount": sender,
                                 "toUserAccount": receiver,
                                 "amount": 500_000_000}]}


def test_known_cex_address_is_root_like():
    any_cex = next(iter(CEX_ADDRESSES))
    assert is_root_like(any_cex, tx_count=3) is True


def test_high_transaction_count_is_root_like():
    assert is_root_like("Whatever", FUNDING_ROOT_TX_COUNT + 1) is True


def test_ordinary_relay_wallet_is_not_root_like():
    assert is_root_like("Relay1", tx_count=30) is False


async def test_funder_of_returns_the_sending_wallet(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {"Buyer1": [_funding_tx("Relay1", "Buyer1")]}
    async with make_client(enhanced=enhanced) as c:
        parent, is_root = await funder_of(RpcClient(c, "k"), store, "Buyer1")
    assert parent == "Relay1"
    assert is_root is False
    store.close()


async def test_funder_of_uses_cache_on_second_call(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {"Buyer1": [_funding_tx("Relay1", "Buyer1")]}
    async with make_client(enhanced=enhanced) as c:
        rpc = RpcClient(c, "k")
        await funder_of(rpc, store, "Buyer1")
    # Second call with an RPC that would fail if actually used.
    async with make_client(enhanced={}) as c2:
        parent, _ = await funder_of(RpcClient(c2, "k"), store, "Buyer1")
    assert parent == "Relay1"
    store.close()


async def test_resolve_roots_collapses_a_cabal(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {f"B{i}": [_funding_tx("Relay1", f"B{i}")] for i in range(6)}
    enhanced["Relay1"] = [_funding_tx("Whale", "Relay1")]
    enhanced["Whale"] = []
    async with make_client(enhanced=enhanced) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store,
                                    [f"B{i}" for i in range(6)], hops=2)
    assert len(set(roots.values())) == 1
    result = funding_entropy(roots)
    assert result.h_norm < 0.01
    store.close()


async def test_cex_funded_buyers_stay_distinct(tmp_path):
    """The false-alarm trap: independent buyers all funded from one exchange
    must NOT collapse into a single root."""
    store = Store(tmp_path / "t.db")
    cex = next(iter(CEX_ADDRESSES))
    enhanced = {f"B{i}": [_funding_tx(cex, f"B{i}")] for i in range(6)}
    async with make_client(enhanced=enhanced) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store,
                                    [f"B{i}" for i in range(6)], hops=2)
    assert len(set(roots.values())) == 6
    assert funding_entropy(roots).h_norm > 0.99
    store.close()


async def test_busy_wallet_becomes_a_root_and_buyers_stay_distinct(tmp_path):
    """An unlisted aggregator with a huge signature count must behave like a
    CEX: buyers funded from it stay independent rather than collapsing."""
    store = Store(tmp_path / "t.db")
    busy = "BusyAggregator"
    enhanced = {f"B{i}": [_funding_tx(busy, f"B{i}")] for i in range(4)}
    # A full page of transactions triggers the signature count.
    enhanced[busy] = [_funding_tx("X", busy) for _ in range(FUNDING_PAGE_SIZE)]
    rpc_methods = {"getSignaturesForAddress":
                   [{"signature": f"s{i}"} for i in range(FUNDING_ROOT_TX_COUNT)]}
    async with make_client(enhanced=enhanced, rpc_methods=rpc_methods) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store,
                                    [f"B{i}" for i in range(4)], hops=2)
    assert len(set(roots.values())) == 4
    store.close()


async def test_moderately_active_wallet_is_not_a_root(tmp_path):
    """A relay wallet with a full page but few total signatures must still be
    followed through, so real cabals are not missed."""
    store = Store(tmp_path / "t.db")
    relay = "Relay1"
    enhanced = {"B0": [_funding_tx(relay, "B0")],
                relay: [_funding_tx("Whale", relay)
                        for _ in range(FUNDING_PAGE_SIZE)],
                "Whale": []}
    rpc_methods = {"getSignaturesForAddress":
                   [{"signature": f"s{i}"} for i in range(120)]}
    async with make_client(enhanced=enhanced, rpc_methods=rpc_methods) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B1"],
                                    hops=2)
    assert roots["B0"] == "Whale"
    store.close()


async def test_unresolvable_buyer_maps_to_itself(tmp_path):
    store = Store(tmp_path / "t.db")
    async with make_client(enhanced={"B0": [], "B1": []}) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B1"])
    assert roots["B0"] == "B0"
    assert roots["B1"] == "B1"
    store.close()


async def test_walk_stops_at_hop_limit(tmp_path):
    store = Store(tmp_path / "t.db")
    enhanced = {"B0": [_funding_tx("L1", "B0")],
                "L1": [_funding_tx("L2", "L1")],
                "L2": [_funding_tx("L3", "L2")],
                "L3": []}
    async with make_client(enhanced=enhanced) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B0x"],
                                    hops=2)
    assert roots["B0"] == "L2"  # two hops, not three
    store.close()


async def test_rpc_failure_does_not_crash_the_walk(tmp_path):
    store = Store(tmp_path / "t.db")
    async with make_client(enhanced={"B0": 500}) as c:
        roots = await resolve_roots(RpcClient(c, "k"), store, ["B0", "B1"])
    assert roots["B0"] == "B0"
    store.close()
