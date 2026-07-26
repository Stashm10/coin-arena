import asyncio
import threading
from typing import Callable

import httpx

from arena.engine import check_mint
from arena.models import ScanResult
from arena.settings import Settings
from arena.store import Store


async def _scan_async(mint: str, settings: Settings) -> ScanResult:
    store = Store()
    try:
        async with httpx.AsyncClient() as client:
            return await check_mint(mint, settings, store, client)
    finally:
        store.close()


def _default_scan(mint: str, settings: Settings) -> ScanResult:
    # Fresh event loop per call — safe because this runs on a worker thread.
    return asyncio.run(_scan_async(mint, settings))


def run_scan(mint: str, settings: Settings,
             on_done: Callable[[ScanResult], None],
             on_error: Callable[[Exception], None],
             scan_fn: Callable[[str, Settings], ScanResult] | None = None
             ) -> threading.Thread:
    """Run a scan off the UI thread. Calls on_done/on_error FROM the worker
    thread — the caller (view) must marshal UI updates back with
    page.run_thread(). No flet import here on purpose."""
    fn = scan_fn or _default_scan

    def worker() -> None:
        try:
            on_done(fn(mint, settings))
        except Exception as exc:  # includes ValueError (bad mint)
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
