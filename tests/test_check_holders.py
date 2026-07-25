from arena.birth import Birth
from arena.checks import holders
from arena.models import DISQUALIFIER, PASS, WARNING
from arena.rpc import RpcClient
from tests.helpers import make_client

SYSTEM = "11111111111111111111111111111111"


def rpc_methods(amounts_by_owner, supply=1000.0):
    """amounts_by_owner: [(owner, ui_amount, owner_program)] for top accounts."""
    largest = {"value": [
        {"address": f"TA{i}", "uiAmount": amt}
        for i, (_, amt, _) in enumerate(amounts_by_owner)]}
    def multi(params):
        accounts = params[0]
        if accounts and accounts[0].startswith("TA"):  # token accounts -> owners
            return {"value": [
                {"data": {"parsed": {"info": {"owner": amounts_by_owner[int(a[2:])][0]}}}}
                for a in accounts]}
        owner_prog = {o: prog for (o, _, prog) in amounts_by_owner}
        return {"value": [{"owner": owner_prog[a]} for a in accounts]}
    return {
        "getTokenLargestAccounts": largest,
        "getTokenSupply": {"value": {"uiAmount": supply}},
        "getMultipleAccounts": multi,
    }


async def test_concentrated_supply_disqualifies():
    m = rpc_methods([("W1", 300, SYSTEM), ("W2", 300, SYSTEM)], supply=1000)
    async with make_client(m) as c:  # top-10 human share = 0.6 > 0.55
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == DISQUALIFIER
    assert f.data["top10_share"] == 0.6
    assert f.data["owners"] == ["W1", "W2"]


async def test_pool_excluded_and_single_holder_warning():
    m = rpc_methods([("Pool", 800, "RaydiumProgram111"), ("W1", 200, SYSTEM)],
                    supply=1000)
    async with make_client(m) as c:  # human share 0.2, but W1 alone 0.2 > 0.15
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == WARNING and f.data["max_single"] == 0.2


async def test_dispersed_supply_passes():
    m = rpc_methods([(f"W{i}", 20, SYSTEM) for i in range(10)], supply=1000)
    async with make_client(m) as c:  # 0.2 total, max single 0.02
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == PASS


async def test_no_holder_data_keeps_full_data_contract():
    m = {"getTokenLargestAccounts": {"value": []},
         "getTokenSupply": {"value": {"uiAmount": 0}}}
    async with make_client(m) as c:
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == PASS
    assert f.data == {"top10_share": 0.0, "max_single": 0.0, "owners": []}


async def test_owners_ranked_by_combined_holdings():
    # W2 holds two smaller accounts summing larger than W1's single account
    m = rpc_methods([("W1", 300, SYSTEM), ("W2", 200, SYSTEM), ("W2", 200, SYSTEM)],
                    supply=10000)
    async with make_client(m) as c:
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.data["owners"] == ["W2", "W1"]
    assert f.data["max_single"] == 0.04
