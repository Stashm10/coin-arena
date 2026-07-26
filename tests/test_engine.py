import pytest

from arena.__main__ import print_result  # ensure it doesn't raise on hostile input
from arena.engine import check_mint
from arena.settings import Settings
from arena.store import Store
from tests.helpers import make_client

GOOD_MINT = "6dkGZgkn8Togra9BJeZkyAtZAGxNEQUF7sVzY8Tqpump"
SYSTEM = "11111111111111111111111111111111"

CLEAN_RPC = {
    "getAccountInfo": {"value": {"data": {"parsed": {"info": {
        "mintAuthority": None, "freezeAuthority": None}}}}},
    "getTokenLargestAccounts": {"value": [{"address": "TA0", "uiAmount": 10.0}]},
    "getTokenSupply": {"value": {"uiAmount": 1000.0}},
    "getMultipleAccounts": lambda params: (
        {"value": [{"data": {"parsed": {"info": {"owner": "W1"}}}}]}
        if params[0][0].startswith("TA") else {"value": [{"owner": SYSTEM}]}),
    "getSignaturesForAddress": [{"signature": "s1", "slot": 1, "blockTime": 100}],
    "getTokenAccounts": {"token_accounts": []},
}
ENHANCED = {"__by_sig__": {"s1": {"signature": "s1", "feePayer": "Dev",
                                  "slot": 1, "timestamp": 100,
                                  "tokenTransfers": [], "nativeTransfers": []}},
            "Dev": []}
DS = {GOOD_MINT: {"pairs": [{"priceUsd": "0.002", "liquidity": {"usd": 5000},
                             "baseToken": {"symbol": "TEST"}}]}}


async def test_invalid_mint_raises_valueerror(tmp_path):
    store = Store(tmp_path / "a.db")
    async with make_client() as c:
        with pytest.raises(ValueError):
            await check_mint("not-a-mint!!", Settings("k"), store, c)


async def test_clean_coin_end_to_end(tmp_path):
    store = Store(tmp_path / "a.db")
    async with make_client(CLEAN_RPC, enhanced=ENHANCED, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.verdict == "NO_RED_FLAGS"
    assert r.symbol == "TEST" and r.price_usd == 0.002
    assert len(r.findings) == 6
    assert store.recent_scans()[0]["mint"] == GOOD_MINT


async def test_rug_pattern_is_avoid(tmp_path):
    rug_rpc = dict(CLEAN_RPC)
    rug_rpc["getAccountInfo"] = {"value": {"data": {"parsed": {"info": {
        "mintAuthority": "Dev", "freezeAuthority": None}}}}}
    store = Store(tmp_path / "a.db")
    async with make_client(rug_rpc, enhanced=ENHANCED, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.verdict == "AVOID"


async def test_public_mode_still_scans(tmp_path):
    store = Store(tmp_path / "a.db")
    public_rpc = dict(CLEAN_RPC)
    public_rpc["getTransaction"] = {"transaction": {"message": {"accountKeys": [
        {"pubkey": "Dev"}]}}}
    async with make_client(public_rpc, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings(None), store, c)
    assert r.verdict in ("NO_RED_FLAGS", "CAUTION")
    assert r.unavailable >= 2  # bundles, dev_record at minimum


async def test_scan_survives_save_scan_failure(tmp_path):
    store = Store(tmp_path / "a.db")

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    store.save_scan = boom
    async with make_client(CLEAN_RPC, enhanced=ENHANCED, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.verdict == "NO_RED_FLAGS"
    assert len(r.findings) == 6


async def test_scan_survives_non_dict_dexscreener_body(tmp_path):
    # DexScreener returning valid JSON that isn't a dict (e.g. a bare array)
    # must not escape as a raw AttributeError — check_mint stays never-raise
    # and just treats the pair as unavailable.
    store = Store(tmp_path / "a.db")
    async with make_client(CLEAN_RPC, enhanced=ENHANCED,
                           dexscreener={GOOD_MINT: []}) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.price_usd is None and r.symbol is None
    assert len(r.findings) == 6


def test_print_result_survives_markup_in_symbol_and_evidence(capsys):
    from arena.models import Finding, ScanResult
    r = ScanResult(mint="M"*40, verdict="NO_RED_FLAGS",
                   findings=[Finding("vitals", "INFO", "age [not a tag] 3m", {})],
                   unavailable=0, price_usd=None, symbol="[red]evil[/red]", duration_s=1.0)
    print_result(r)  # must not raise MarkupError
    out = capsys.readouterr().out
    assert "evil" in out
