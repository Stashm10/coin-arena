from arena.birth import Birth
from arena.checks import funding
from arena.models import DISQUALIFIER, INFO, PASS
from arena.rpc import RpcClient
from arena.store import Store
from tests.helpers import make_client

B = Birth(creator="Dev")
FUND_TX = {"__by_sig__": {"f1": {"signature": "f1", "nativeTransfers": [
    {"fromUserAccount": "Funder1", "toUserAccount": "Dev", "amount": 5000000}]}}}
SIGS = [{"signature": "f2"}, {"signature": "f1"}]  # newest-first; f1 = oldest


async def test_known_rugger_funder_disqualifies(tmp_path):
    store = Store(tmp_path / "a.db")
    from arena.models import Finding, ScanResult
    store.save_scan(ScanResult("OldRug", "AVOID", [], 0, None, None, 0),
                    creator=None, funder="Funder1", top_holders=[])
    store.record_outcome("OldRug", "RUGGED")
    async with make_client({"getSignaturesForAddress": SIGS}, enhanced=FUND_TX) as c:
        f = await funding.run(RpcClient(c, "k"), store, "M", B, None)
    assert f.severity == DISQUALIFIER and f.data["funder"] == "Funder1"


async def test_clean_funder_passes(tmp_path):
    store = Store(tmp_path / "a.db")
    async with make_client({"getSignaturesForAddress": SIGS}, enhanced=FUND_TX) as c:
        f = await funding.run(RpcClient(c, "k"), store, "M", B, None)
    assert f.severity == PASS and f.data["funder"] == "Funder1"


async def test_busy_wallet_is_info(tmp_path):
    store = Store(tmp_path / "a.db")
    sigs = [{"signature": f"s{i}"} for i in range(1000)]
    async with make_client({"getSignaturesForAddress": sigs}) as c:
        f = await funding.run(RpcClient(c, "k"), store, "M", B, None)
    assert f.severity == INFO and "too active" in f.evidence
