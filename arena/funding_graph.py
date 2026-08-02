"""Backward k-hop walk from launch buyers to their funding roots.

THE TRAP THIS AVOIDS: a naive walk collapses every Coinbase-funded wallet into
one root, craters entropy, and reports "cabal" on a launch full of genuinely
independent retail buyers. The walk therefore terminates at root-like nodes —
known exchange addresses, or wallets with implausibly many transactions — and
counts each as its own distinct source. A relay wallet has tens of
transactions; an exchange hot wallet has millions.

Cost: FUNDING_GRAPH_MAX_BUYERS x FUNDING_GRAPH_HOPS requests, which is why the
caller exposes this behind an explicit button rather than running it on every
scan. Resolved edges are cached in SQLite.

Approximation, stated plainly: we take the earliest incoming SOL transfer
visible in the most recent FUNDING_PAGE_SIZE transactions rather than paging to
the true first transaction. For a fresh sniper wallet — which has a handful of
transactions — that IS the funding transaction. Wallets busy enough for the
approximation to break are exactly the wallets the root rule bails out on.
"""

import logging

from arena.rpc import RpcClient
from arena.store import Store
from arena.thresholds import (FUNDING_GRAPH_HOPS, FUNDING_GRAPH_MAX_BUYERS,
                              FUNDING_PAGE_SIZE, FUNDING_ROOT_TX_COUNT)

log = logging.getLogger(__name__)

# Exchange hot wallets and well-known aggregators. Each is a root: many
# unrelated users withdraw from the same address, so shared provenance here is
# not evidence of coordination.
CEX_ADDRESSES = frozenset({
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",   # Binance
    "2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S",   # Coinbase 1
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS",   # Coinbase 2
    "AC5RDfQFmDS1deWZos921JfqscXdByf8BKHs5ACWjtW2",   # Bybit
    "u6PJ8DtQuPFnfmwHbGFULQ4u4EgjDiyYKjVEsynXq2w",    # Gate.io
    "GJRs4FwHtemZ5ZE9x3FNvJ8TMwitKTh21yxdRPqn7npE",   # Kraken
})


def is_root_like(address: str, tx_count: int) -> bool:
    return address in CEX_ADDRESSES or tx_count >= FUNDING_ROOT_TX_COUNT


async def funder_of(rpc: RpcClient, store: Store,
                    address: str) -> tuple[str | None, bool]:
    """(parent, parent_is_root). Parent is None when unresolvable."""
    cached = store.cached_edge(address)
    if cached is not None:
        return cached
    if address in CEX_ADDRESSES:
        store.save_edge(address, None, True)
        return None, True
    try:
        txs = await rpc.enhanced_txs(address, limit=FUNDING_PAGE_SIZE)
    except Exception as exc:
        log.warning("funding hop failed for %s: %s", address, exc)
        return None, False
    # A full page means the wallet MIGHT be busy enough to be an aggregator.
    # Only then is the extra signature count worth an API call; a fresh sniper
    # wallet has a handful of transactions and never pays for this.
    if len(txs) >= FUNDING_PAGE_SIZE:
        try:
            sigs = await rpc.rpc("getSignaturesForAddress",
                                 [address, {"limit": FUNDING_ROOT_TX_COUNT}])
        except Exception as exc:
            log.warning("signature count failed for %s: %s", address, exc)
            sigs = []
        if is_root_like(address, len(sigs or [])):
            store.save_edge(address, None, True)
            return None, True
    parent = None
    for tx in sorted(txs, key=lambda t: t.get("timestamp") or 0):
        for transfer in tx.get("nativeTransfers") or []:
            if (transfer.get("toUserAccount") == address
                    and transfer.get("fromUserAccount")):
                parent = transfer["fromUserAccount"]
                break
        if parent:
            break
    if parent is None:
        store.save_edge(address, None, False)
        return None, False
    parent_is_root = parent in CEX_ADDRESSES
    store.save_edge(address, parent, parent_is_root)
    return parent, parent_is_root


async def resolve_roots(rpc: RpcClient, store: Store, buyers: list[str],
                        hops: int = FUNDING_GRAPH_HOPS) -> dict[str, str]:
    """Map each buyer to its root funding source. An unresolvable buyer maps to
    ITSELF — not knowing where a wallet's money came from is not evidence that
    it shares a source with another unknown wallet."""
    roots: dict[str, str] = {}
    for buyer in buyers[:FUNDING_GRAPH_MAX_BUYERS]:
        current = buyer
        for _ in range(hops):
            parent, is_root = await funder_of(rpc, store, current)
            if parent is None:
                # `current` itself resolved as root-like (CEX membership or
                # tx-count), not just unresolvable. Root-like means "shared
                # venue, not shared identity" — attribute this buyer to
                # itself rather than to the aggregator/exchange address.
                # When unresolvable (is_root False), leave current as the
                # last node actually reached.
                if is_root:
                    current = buyer
                break
            if is_root:
                # The exchange is a root, but each withdrawal is independent —
                # attribute this buyer to itself, not to the exchange.
                current = buyer
                break
            current = parent
        roots[buyer] = current
    return roots
