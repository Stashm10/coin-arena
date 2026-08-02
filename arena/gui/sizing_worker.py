"""Off-thread runners for the sizing calculator and the tip lookup. Same
contract as scan_worker.run_scan: callbacks fire FROM the worker thread."""

import asyncio
import threading
from typing import Callable

import httpx

from arena.flow.kelly import KellyInputs, KellyResult, solve_kelly
from arena.flow.tips import TipFloor, fetch_tips


def run_kelly(inputs: KellyInputs, on_done: Callable[[KellyResult], None],
              on_error: Callable[[Exception], None], solve_fn=None
              ) -> threading.Thread:
    fn = solve_fn or solve_kelly

    def worker() -> None:
        try:
            on_done(fn(inputs))
        except Exception as exc:
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


async def _tips_async() -> TipFloor:
    async with httpx.AsyncClient() as client:
        return await fetch_tips(client)


def run_tips(on_done: Callable[[TipFloor], None],
             on_error: Callable[[Exception], None], fetch_fn=None
             ) -> threading.Thread:
    fn = fetch_fn or (lambda: asyncio.run(_tips_async()))

    def worker() -> None:
        try:
            on_done(fn())
        except Exception as exc:
            on_error(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
