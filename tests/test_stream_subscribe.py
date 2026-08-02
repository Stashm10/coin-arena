import base64
import json
import struct
import time

from arena.stream.subscribe import (parse_notification, subscription_payload,
                                    watch, ws_url)


def _payload():
    return base64.b64encode(
        b"\x00" * 8 + bytes(range(32)) + struct.pack("<QQ?", 10**9, 10**9, True)
        + bytes(range(32, 64))
        + struct.pack("<qQQ", 1_754_000_000, 30 * 10**9, 10**12)).decode()


def _notification(logs):
    return json.dumps({
        "jsonrpc": "2.0", "method": "logsNotification",
        "params": {"result": {"value": {"signature": "sig", "err": None,
                                        "logs": logs}}}})


class FakeSocket:
    """Yields queued messages then raises to simulate a dropped connection."""

    def __init__(self, messages, fail_after=True):
        self.messages = list(messages)
        self.fail_after = fail_after
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        if self.fail_after:
            raise ConnectionError("socket closed")
        raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class Stop:
    def __init__(self, after=1):
        self.calls = 0
        self.after = after

    def is_set(self):
        self.calls += 1
        return self.calls > self.after


class WaitStop:
    """Mimics threading.Event: exposes both is_set() and a wait(timeout)
    that returns True immediately, to prove watch() prefers the blocking
    wait over asyncio.sleep when it is available."""

    def __init__(self):
        self.calls = 0
        self.wait_calls = []

    def is_set(self):
        self.calls += 1
        return self.calls > 1

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        return True


def test_ws_url_uses_helius_mainnet_and_key():
    url = ws_url("KEY123")
    assert url.startswith("wss://")
    assert "KEY123" in url


def test_subscription_payload_targets_the_mint():
    payload = subscription_payload("MintABC")
    assert payload["method"] == "logsSubscribe"
    assert payload["params"][0] == {"mentions": ["MintABC"]}
    assert payload["params"][1]["commitment"] == "processed"


def test_parse_notification_extracts_a_buy():
    msg = _notification(["Program log: Instruction: Buy",
                         f"Program data: {_payload()}"])
    event = parse_notification(msg, now=123.0)
    assert event is not None
    assert event.ts == 123.0  # locally stamped arrival time
    assert event.is_buy is True
    assert event.price > 0


def test_parse_notification_ignores_non_trade_logs():
    msg = _notification(["Program log: Instruction: Create"])
    assert parse_notification(msg, now=1.0) is None


def test_parse_notification_ignores_failed_transactions():
    msg = json.dumps({"params": {"result": {"value": {
        "signature": "s", "err": {"InstructionError": [0, "X"]},
        "logs": ["Program log: Instruction: Buy",
                 f"Program data: {_payload()}"]}}}})
    assert parse_notification(msg, now=1.0) is None


def test_parse_notification_ignores_subscription_confirmation():
    assert parse_notification(json.dumps({"result": 42, "id": 1}), now=1.0) is None


def test_parse_notification_survives_garbage():
    assert parse_notification("not json", now=1.0) is None


async def test_watch_sends_subscription_and_emits_events():
    msg = _notification(["Program log: Instruction: Buy",
                         f"Program data: {_payload()}"])
    socket = FakeSocket([msg], fail_after=False)
    events, states = [], []

    async def connect(url):
        return socket

    await watch("KEY", "MintABC", on_event=events.append,
                on_disconnect=lambda: states.append("down"),
                on_reconnect=lambda: states.append("up"),
                stop=Stop(after=1), connect=connect)

    assert len(events) == 1
    sent = json.loads(socket.sent[0])
    assert sent["params"][0] == {"mentions": ["MintABC"]}


async def test_watch_reports_disconnect_then_reconnect():
    socket_a = FakeSocket([], fail_after=True)
    socket_b = FakeSocket([], fail_after=False)
    sockets = [socket_a, socket_b]
    states = []

    async def connect(url):
        return sockets.pop(0)

    await watch("KEY", "M", on_event=lambda e: None,
                on_disconnect=lambda: states.append("down"),
                on_reconnect=lambda: states.append("up"),
                stop=Stop(after=2), connect=connect)

    assert "down" in states
    assert states.index("down") < states.index("up")


async def test_watch_stops_when_stop_is_set():
    calls = {"n": 0}

    async def connect(url):
        calls["n"] += 1
        return FakeSocket([], fail_after=False)

    class AlwaysStop:
        def is_set(self):
            return True

    await watch("KEY", "M", on_event=lambda e: None,
                on_disconnect=lambda: None, on_reconnect=lambda: None,
                stop=AlwaysStop(), connect=connect)
    assert calls["n"] == 0


async def test_watch_uses_stop_wait_for_backoff_when_available():
    """When stop exposes a callable wait(timeout) (as threading.Event does),
    watch must use it instead of a plain asyncio.sleep, so shutdown during
    the reconnect backoff is noticed immediately rather than after up to
    BACKOFF_MAX_S seconds."""
    socket = FakeSocket([], fail_after=True)

    async def connect(url):
        return socket

    stop = WaitStop()
    started = time.monotonic()
    await watch("KEY", "M", on_event=lambda e: None,
                on_disconnect=lambda: None, on_reconnect=lambda: None,
                stop=stop, connect=connect)
    elapsed = time.monotonic() - started

    assert stop.wait_calls == [1.0]  # called with BACKOFF_START_S
    assert elapsed < 0.5  # returned promptly, did not sleep the backoff
