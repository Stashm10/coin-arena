from arena.birth import Birth
from arena.models import DISQUALIFIER, INFO, PASS, WARNING, Finding
from arena.prices import PairInfo
from arena.rpc import RpcClient
from arena.thresholds import (DEV_HISTORY_SAMPLE, DEV_LAUNCHES_DISQUALIFIER,
                              DEV_LAUNCHES_WARNING)


def _is_creation(tx: dict) -> bool:
    return tx.get("type") == "TOKEN_MINT" or (
        tx.get("source") == "PUMP_FUN" and tx.get("type") == "CREATE")


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    if not birth.creator:
        return Finding("dev_record", INFO, "Creator wallet unknown", {})
    history = await rpc.enhanced_txs(birth.creator, limit=DEV_HISTORY_SAMPLE)
    prior = 0
    for tx in history:
        if not _is_creation(tx):
            continue
        mints = {t.get("mint") for t in tx.get("tokenTransfers") or []}
        if mint not in mints:
            prior += 1
    data = {"prior_launches": prior, "creator": birth.creator}
    msg = f"Dev launched {prior} prior tokens (sample of last {DEV_HISTORY_SAMPLE} txs)"
    if prior >= DEV_LAUNCHES_DISQUALIFIER:
        return Finding("dev_record", DISQUALIFIER, msg, data)
    if prior >= DEV_LAUNCHES_WARNING:
        return Finding("dev_record", WARNING, msg, data)
    return Finding("dev_record", PASS, msg if prior else "No prior launches found", data)
