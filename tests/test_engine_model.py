import json

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
ENHANCED = {"__by_sig__": {"s1": {"signature": "s1", "feePayer": "Dev", "slot": 1,
                                  "timestamp": 100, "tokenTransfers": [],
                                  "nativeTransfers": []}}, "Dev": []}


async def test_no_model_leaves_probability_none(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    store = Store(tmp_path / "a.db")
    async with make_client(CLEAN_RPC, enhanced=ENHANCED) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.rug_probability is None


async def test_model_present_attaches_probability(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    # Write an 11-feature model (matches FEATURE_NAMES) that leans clean.
    from arena.features import FEATURE_NAMES
    model = {"feature_names": FEATURE_NAMES,
             "means": [0.0] * 11, "stds": [1.0] * 11,
             "coef": [0.0] * 11, "intercept": 0.0,
             "n_samples": 30, "n_rug": 10, "n_clean": 20}
    (tmp_path / "rug_model.json").write_text(json.dumps(model))
    store = Store(tmp_path / "a.db")
    async with make_client(CLEAN_RPC, enhanced=ENHANCED) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.rug_probability is not None
    assert abs(r.rug_probability - 0.5) < 1e-9   # all-zero coef -> 0.5
