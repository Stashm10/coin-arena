"""Helius logsSubscribe client for a single mint.

Disconnection is a first-class event, not an error to swallow: for this engine
an absence of trades IS the signal, so a silently dead socket looks exactly
like a coin going quiet. on_disconnect fires immediately so the UI can suppress
stale numbers.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Protocol

from arena.stream.decode import event_from_logs
from arena.stream.tape import TapeEvent

log = logging.getLogger(__name__)

HELIUS_WS = "wss://mainnet.helius-rpc.com/?api-key={key}"
BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0
PING_INTERVAL_S = 15
PING_TIMEOUT_S = 10


class Disconnected(Exception):
    pass


class StopFlag(Protocol):
    """Duck-typed stop signal — only `.is_set()` is required. If the object
    also exposes a callable `.wait(timeout) -> bool` (as `threading.Event`
    does), `watch` uses it to sleep out the reconnect backoff interruptibly
    instead of a plain `asyncio.sleep`, so shutdown is noticed the instant
    the flag is set rather than after up to BACKOFF_MAX_S seconds."""

    def is_set(self) -> bool: ...


def ws_url(key: str) -> str:
    return HELIUS_WS.format(key=key)


def subscription_payload(mint: str) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
            "params": [{"mentions": [mint]}, {"commitment": "processed"}]}


def parse_notification(message: str, now: float) -> TapeEvent | None:
    """Locally stamped arrival time — carries 50-200ms of network jitter, so
    nothing downstream may claim sub-second precision."""
    try:
        body = json.loads(message)
        value = body["params"]["result"]["value"]
    except Exception:
        return None
    if value.get("err") is not None:
        return None
    trade = event_from_logs(value.get("logs") or [])
    if trade is None:
        return None
    return TapeEvent(ts=now, is_buy=trade.is_buy, sol=trade.sol,
                     price=trade.price)


async def _default_connect(url: str):
    import websockets
    return await websockets.connect(url, ping_interval=PING_INTERVAL_S,
                                    ping_timeout=PING_TIMEOUT_S)


async def watch(key: str, mint: str, on_event: Callable[[TapeEvent], None],
                on_disconnect: Callable[[], None],
                on_reconnect: Callable[[], None],
                stop: StopFlag,
                connect: Callable[[str], object] | None = None,
                clock: Callable[[], float] = time.monotonic) -> None:
    connect = connect or _default_connect
    backoff = BACKOFF_START_S
    first = True
    while not stop.is_set():
        try:
            socket = await connect(ws_url(key))
            async with socket:
                await socket.send(json.dumps(subscription_payload(mint)))
                if not first:
                    on_reconnect()
                first = False
                backoff = BACKOFF_START_S
                async for message in socket:
                    event = parse_notification(message, clock())
                    if event is not None:
                        on_event(event)
                    if stop.is_set():
                        return
        except Exception as exc:
            log.warning("stream dropped: %s", exc)
            on_disconnect()
            wait = getattr(stop, "wait", None)
            if callable(wait):
                # Blocking Event.wait() run off-loop so it can return the
                # instant stop is set, instead of sleeping the full backoff.
                await asyncio.get_running_loop().run_in_executor(
                    None, wait, backoff)
            else:
                await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
