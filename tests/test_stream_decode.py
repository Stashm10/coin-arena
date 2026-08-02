import base64
import struct

from arena.stream.decode import decode_trade_event, event_from_logs

MINT = bytes(range(32))
USER = bytes(range(32, 64))


def _payload(sol=1_500_000_000, tokens=2_000_000_000, is_buy=True,
             v_sol=30_000_000_000, v_tok=1_000_000_000_000, extra=b""):
    return base64.b64encode(
        b"\x00" * 8 + MINT + struct.pack("<QQ?", sol, tokens, is_buy) + USER
        + struct.pack("<qQQ", 1_754_000_000, v_sol, v_tok) + extra).decode()


def test_decodes_all_fields():
    ev = decode_trade_event(_payload())
    assert ev is not None
    assert ev.is_buy is True
    assert abs(ev.sol - 1.5) < 1e-9
    assert abs(ev.tokens - 2000.0) < 1e-6
    assert ev.ts == 1_754_000_000
    assert len(ev.mint) >= 32  # base58 of a 32-byte key


def test_price_uses_sol_and_token_decimals():
    ev = decode_trade_event(_payload(v_sol=30_000_000_000, v_tok=1_000_000_000_000))
    # (30e9/1e9) / (1e12/1e6) = 30 / 1e6 = 3e-5 SOL per token
    assert abs(ev.price - 3e-5) < 1e-12


def test_tolerates_trailing_fields_from_newer_program_versions():
    ev = decode_trade_event(_payload(extra=b"\x01" * 48))
    assert ev is not None
    assert abs(ev.sol - 1.5) < 1e-9


def test_sell_flag_decodes():
    assert decode_trade_event(_payload(is_buy=False)).is_buy is False


def test_short_payload_returns_none():
    assert decode_trade_event(base64.b64encode(b"\x00" * 40).decode()) is None


def test_garbage_base64_returns_none():
    assert decode_trade_event("!!!not base64!!!") is None


def test_zero_reserves_returns_none():
    assert decode_trade_event(_payload(v_tok=0)) is None


def test_event_from_logs_requires_a_trade_instruction():
    logs = ["Program log: Instruction: Create", f"Program data: {_payload()}"]
    assert event_from_logs(logs) is None


def test_event_from_logs_picks_the_trade_payload():
    logs = ["Program log: Instruction: Buy",
            "Program data: c2hvcnQ=",
            f"Program data: {_payload()}"]
    ev = event_from_logs(logs)
    assert ev is not None and ev.is_buy is True


def test_event_from_logs_returns_none_without_payload():
    assert event_from_logs(["Program log: Instruction: Sell"]) is None


def test_all_zero_pubkey_encodes_to_canonical_32_ones():
    # Pubkey::default() (32 zero bytes) is a real value seen in Solana
    # account data (e.g. the System Program ID) and base58-encodes to
    # exactly 32 '1' characters, not 33.
    payload = base64.b64encode(
        b"\x00" * 8 + b"\x00" * 32
        + struct.pack("<QQ?", 1_500_000_000, 2_000_000_000, True) + USER
        + struct.pack("<qQQ", 1_754_000_000, 30_000_000_000, 1_000_000_000_000)
    ).decode()
    ev = decode_trade_event(payload)
    assert ev is not None
    assert ev.mint == "1" * 32
