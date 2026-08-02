"""Runs the funding-graph walk off the UI thread. Same contract as
scan_worker.run_scan: callbacks fire FROM the worker thread."""

import asyncio
import threading
from typing import Callable

import httpx

from arena.funding_graph import resolve_roots
from arena.rpc import RpcClient
from arena.settings import Settings
from arena.store import Store


async def _trace_async(buyers: list[str], settings: Settings) -> dict[str, str]:
    store = Store()
    try:
        async with httpx.AsyncClient() as client:
            return await resolve_roots(RpcClient(client, settings.helius_key),
                                       store, buyers)
    finally:
        store.close()


def _default_trace(mint: str, buyers: list[str], settings: Settings) -> dict:
    return asyncio.run(_trace_async(buyers, settings))


def run_trace(mint: str, buyers: list[str], settings: Settings,
              on_done: Callable[[dict], None],
              on_error: Callable[[Exception], None],
              trace_fn=None) -> threading.Thread:
    fn = trace_fn or _default_trace

    def worker() -> None:
        try:
            on_done(fn(mint, buyers, settings))
        except Exception as exc:
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
