from arena.birth import Birth
from arena.models import DISQUALIFIER, PASS, Finding
from arena.prices import PairInfo
from arena.rpc import RpcClient


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    result = await rpc.rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    info = result["value"]["data"]["parsed"]["info"]
    mint_auth = info.get("mintAuthority") is not None
    freeze_auth = info.get("freezeAuthority") is not None
    data = {"mint_authority": mint_auth, "freeze_authority": freeze_auth}
    if mint_auth:
        return Finding("authorities", DISQUALIFIER,
                       "Mint authority not revoked — dev can print supply", data)
    if freeze_auth:
        return Finding("authorities", DISQUALIFIER,
                       "Freeze authority not revoked — dev can block selling", data)
    return Finding("authorities", PASS, "Mint & freeze authority revoked", data)
