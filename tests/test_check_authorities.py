from arena.birth import Birth
from arena.checks import authorities
from arena.models import DISQUALIFIER, PASS
from arena.rpc import RpcClient
from tests.helpers import make_client


def acct(mint_auth, freeze_auth):
    return {"value": {"data": {"parsed": {"info": {
        "mintAuthority": mint_auth, "freezeAuthority": freeze_auth,
        "decimals": 6, "supply": "1000"}}}}}


async def test_live_mint_authority_disqualifies():
    async with make_client({"getAccountInfo": acct("DevKey", None)}) as c:
        f = await authorities.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == DISQUALIFIER and "print" in f.evidence


async def test_freeze_authority_disqualifies():
    async with make_client({"getAccountInfo": acct(None, "DevKey")}) as c:
        f = await authorities.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == DISQUALIFIER and "block selling" in f.evidence


async def test_both_revoked_passes():
    async with make_client({"getAccountInfo": acct(None, None)}) as c:
        f = await authorities.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == PASS
    assert f.data == {"mint_authority": False, "freeze_authority": False}
