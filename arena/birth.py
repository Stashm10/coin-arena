import logging
from dataclasses import dataclass, field

from arena.rpc import FeatureUnavailable, RpcClient, RpcError

log = logging.getLogger(__name__)

MAX_SIG_PAGES = 5
KEEP_SIGS = 200
KEEP_TXS = 40


@dataclass
class Birth:
    creation_sig: str | None = None
    creator: str | None = None
    created_ts: int | None = None
    first_sig_infos: list[dict] = field(default_factory=list)
    first_txs: list[dict] = field(default_factory=list)


async def fetch_birth(rpc: RpcClient, mint: str) -> Birth:
    """Locate the coin's creation and earliest activity. Best-effort:
    partial data on failure, never raises."""
    birth = Birth()
    try:
        page = await rpc.rpc("getSignaturesForAddress", [mint, {"limit": 1000}])
        if not isinstance(page, list):
            return birth
        pages = 1
        while len(page) == 1000 and pages < MAX_SIG_PAGES:
            older = await rpc.rpc("getSignaturesForAddress",
                                  [mint, {"limit": 1000, "before": page[-1]["signature"]}])
            if not isinstance(older, list) or not older:
                break
            page = older
            pages += 1
    except (RpcError, TypeError, KeyError, IndexError) as exc:
        log.warning("birth: signature fetch failed for %s: %s", mint, exc)
        return birth

    if not page:
        return birth

    try:
        oldest_first = list(reversed(page))[:KEEP_SIGS]
        birth.first_sig_infos = oldest_first
        birth.creation_sig = oldest_first[0]["signature"]
        birth.created_ts = oldest_first[0].get("blockTime")
    except (TypeError, KeyError, IndexError) as exc:
        log.warning("birth: malformed signatures for %s: %s", mint, exc)
        return birth

    try:
        sigs = [s["signature"] for s in oldest_first[:KEEP_TXS]]
        txs = await rpc.enhanced_batch(sigs)
        by_sig = {t.get("signature"): t for t in txs if isinstance(t, dict)}
        birth.first_txs = [by_sig[s] for s in sigs if s in by_sig]
        creation = by_sig.get(birth.creation_sig)
        if creation:
            birth.creator = creation.get("feePayer")
    except FeatureUnavailable:
        try:  # public mode: fee payer via standard getTransaction
            tx = await rpc.rpc("getTransaction", [
                birth.creation_sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            keys = tx["transaction"]["message"]["accountKeys"]
            birth.creator = keys[0]["pubkey"]
        except (RpcError, KeyError, IndexError, TypeError):
            pass
    except RpcError as exc:
        log.warning("birth: enhanced batch failed for %s: %s", mint, exc)
    return birth
