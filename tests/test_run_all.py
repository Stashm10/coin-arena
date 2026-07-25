from arena.birth import Birth
from arena.checks import run_all_checks
from arena.models import CHECK_NAMES, INFO
from arena.rpc import RpcClient
from arena.store import Store
from tests.helpers import make_client


async def test_public_mode_never_raises_and_orders_findings(tmp_path):
    store = Store(tmp_path / "a.db")
    m = {"getSignaturesForAddress": [], "getAccountInfo": 500,
         "getTokenLargestAccounts": 500, "getTokenSupply": 500}
    async with make_client(m) as c:  # everything fails or is keyless
        findings = await run_all_checks(RpcClient(c, None), store, "M", Birth(), None)
    assert [f.check for f in findings] == CHECK_NAMES
    assert all(f.severity == INFO for f in findings[:5])  # vitals also INFO
    assert any("needs Helius key" in f.evidence for f in findings)
