"""Decode pump.fun TradeEvent payloads emitted as `Program data:` log lines.

The 113-byte prefix layout is stable across program versions; newer versions
append fields, so we parse the prefix and ignore the tail. The discriminator is
deliberately NOT validated — it changes between IDL revisions — so callers gate
on the `Instruction: Buy`/`Sell` log line instead.
"""

import base64
import struct
from dataclasses import dataclass

MIN_EVENT_BYTES = 113
_HEADER = 8
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRADE_MARKERS = ("Instruction: Buy", "Instruction: Sell")

SOL_DECIMALS = 1e9
TOKEN_DECIMALS = 1e6


@dataclass
class TradeEvent:
    mint: str
    sol: float
    tokens: float
    is_buy: bool
    user: str
    ts: int
    v_sol: float
    v_tok: float
    price: float


def _b58(raw: bytes) -> str:
    """Base58-encode a public key. Leading zero bytes become leading '1'
    characters, since base58's alphabet has no digit for zero.

    Note: when raw is entirely zero bytes (e.g. Pubkey::default(), which does
    appear as a real value in Solana account data), the numeric value is 0,
    so the digit loop produces no output and every byte's "zero-ness" is
    already represented by `pad` leading '1's -- no extra '1' is appended.
    """
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + out


def decode_trade_event(payload_b64: str) -> TradeEvent | None:
    """Decode a base64 `Program data:` payload into a TradeEvent.

    Returns None if the payload is not valid base64, too short to contain
    the 113-byte TradeEvent prefix, or has non-positive reserves (which
    would make price undefined).
    """
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception:
        return None
    if len(raw) < MIN_EVENT_BYTES:
        return None
    o = _HEADER
    mint = raw[o:o + 32]
    o += 32
    sol, tokens, is_buy = struct.unpack_from("<QQ?", raw, o)
    o += 17
    user = raw[o:o + 32]
    o += 32
    ts, v_sol, v_tok = struct.unpack_from("<qQQ", raw, o)
    if v_sol <= 0 or v_tok <= 0:
        return None
    price = (v_sol / SOL_DECIMALS) / (v_tok / TOKEN_DECIMALS)
    return TradeEvent(mint=_b58(mint), sol=sol / SOL_DECIMALS,
                       tokens=tokens / TOKEN_DECIMALS, is_buy=bool(is_buy),
                       user=_b58(user), ts=ts, v_sol=v_sol / SOL_DECIMALS,
                       v_tok=v_tok / TOKEN_DECIMALS, price=price)


def event_from_logs(logs: list[str]) -> TradeEvent | None:
    """Return the trade event from a log array, or None if this transaction
    was not a buy/sell."""
    if not any(m in line for line in logs for m in _TRADE_MARKERS):
        return None
    marker = "Program data: "
    for line in logs:
        if marker in line:
            event = decode_trade_event(line.split(marker, 1)[1].strip())
            if event is not None:
                return event
    return None
