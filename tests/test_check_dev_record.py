from arena.birth import Birth
from arena.checks import dev_record
from arena.models import DISQUALIFIER, INFO, PASS, WARNING
from arena.rpc import RpcClient
from tests.helpers import make_client


def creation(sig, source="PUMP_FUN", tx_type="CREATE", mint="OldMint"):
    return {"signature": sig, "type": tx_type, "source": source,
            "tokenTransfers": [{"mint": mint}]}


async def test_serial_launcher_disqualifies():
    history = [creation(f"c{i}") for i in range(9)]
    async with make_client(enhanced={"Dev": history}) as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "NewMint",
                                 Birth(creator="Dev"), None)
    assert f.severity == DISQUALIFIER and f.data["prior_launches"] == 9


async def test_three_launches_warns():
    history = [creation(f"c{i}") for i in range(3)] + [
        {"signature": "x", "type": "SWAP", "source": "RAYDIUM", "tokenTransfers": []}]
    async with make_client(enhanced={"Dev": history}) as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "NewMint",
                                 Birth(creator="Dev"), None)
    assert f.severity == WARNING and f.data["prior_launches"] == 3


async def test_current_mint_excluded_and_clean_dev_passes():
    history = [creation("c0", mint="NewMint")]  # only the current launch
    async with make_client(enhanced={"Dev": history}) as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "NewMint",
                                 Birth(creator="Dev"), None)
    assert f.severity == PASS and f.data["prior_launches"] == 0


async def test_unknown_creator_is_info():
    async with make_client() as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == INFO
