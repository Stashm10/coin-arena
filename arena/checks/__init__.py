import asyncio
import logging

from arena.birth import Birth
from arena.checks import (authorities, bundles, dev_record, funding, holders,
                          vitals)
from arena.models import INFO, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient, redact
from arena.store import Store
from arena.thresholds import CHECK_TIMEOUT_S

log = logging.getLogger(__name__)

_CHECKS = [("authorities", authorities), ("holders", holders),
           ("bundles", bundles), ("dev_record", dev_record),
           ("funding", funding), ("vitals", vitals)]


async def run_all_checks(rpc: RpcClient, store: Store, mint: str, birth: Birth,
                         pair: PairInfo | None) -> list[Finding]:
    async def guarded(name, module) -> Finding:
        try:
            return await asyncio.wait_for(
                module.run(rpc, store, mint, birth, pair), CHECK_TIMEOUT_S)
        except FeatureUnavailable as exc:
            return Finding(name, INFO, str(exc), {})
        except asyncio.TimeoutError:
            return Finding(name, INFO, "check unavailable (timeout)", {})
        except Exception as exc:
            log.warning("check %s failed: %s", name, redact(str(exc)))
            return Finding(name, INFO,
                           f"check unavailable ({redact(str(exc))[:80]})", {})

    return list(await asyncio.gather(*(guarded(n, m) for n, m in _CHECKS)))
