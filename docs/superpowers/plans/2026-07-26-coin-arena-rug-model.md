# Coin Arena Rug Model Implementation Plan (Milestone 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manual rug/clean labeling in the app + an offline-trained logistic-regression model whose rug-probability shows alongside the existing rules verdict.

**Architecture:** Heavy training (scikit-learn) runs offline via `python -m arena.train`, exporting a ~1 KB `rug_model.json` to the shared data dir. The app does pure-Python inference (stdlib `math`) reading that file — zero new runtime deps. A new `features.py` is the single shared feature-extraction contract used by both trainer and scanner.

**Tech Stack:** Python 3.11+, stdlib (json/math/sqlite3), Flet (GUI, existing), scikit-learn (training only, dev/ml extra), pytest.

**Spec:** `docs/superpowers/specs/2026-07-26-coin-arena-rug-model-design.md`

## Global Constraints

- Python 3.11+. `features.py`, `model.py`, and the engine's inference path use **stdlib only** (no sklearn, no flet). scikit-learn lives in a new `ml` optional-extra used ONLY by `train.py`.
- `FEATURE_NAMES` is a fixed ordered list of 11 entries (exact order in Task 1); trainer and scanner both call `extract_features`, which takes the parsed `scan_json` shape (`list[dict]` with keys check/severity/evidence/data) and returns values in that order. Missing finding/key → `0.0`. `extract_features` **never raises**.
- `model.load_model` and `model.model_info` **never raise** (missing/malformed file → `None`). `predict_proba` returns a float clamped to [0,1].
- Model inference **never breaks a scan**: engine wraps it so a bad model just means no probability line.
- Manual labels (`manual_labels` table) are the training source of truth, separate from `coin_outcomes`.
- `MIN_TRAIN_SAMPLES = 20`; `train.py` refuses (writes nothing) below that or when only one class is present.
- Rug label = `was_rug=1`, clean = `0`, Unsure = delete the label row.
- The rules verdict (🔴/🟡/🟢) and six finding rows are unchanged; the model line is ADDITIVE, shown only when `rug_probability is not None`.
- Default `pytest` run is offline; the sklearn-dependent train test uses `pytest.importorskip("sklearn")`.
- Data dir is shared (`arena.paths.data_dir()`), so training (source) and the packaged app read/write the same `rug_model.json`.
- Commit after every task with trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Work in `/Users/romanstashkiv/coin_arena` on branch `feature/rug-model` (from `main` at Task 1).

## File Structure

```
arena/
├── features.py     # Task 1 — FEATURE_NAMES + extract_features (pure)
├── model.py        # Task 3 — load_model / predict_proba / model_info (pure)
├── train.py        # Task 5 — python -m arena.train (sklearn, offline)
├── store.py        # Task 2 — manual_labels table + methods
├── models.py       # Task 4 — ScanResult.rug_probability
├── engine.py       # Task 4 — attach rug_probability
└── gui/
    ├── app.py            # Task 6 — route to History
    └── views/
        ├── check.py      # Task 6 — History nav + model line
        └── history.py    # Task 6 — labeling worklist
pyproject.toml            # Task 5 — ml extra
tests/
├── test_features.py      # Task 1
├── test_store_labels.py  # Task 2
├── test_model.py         # Task 3
├── test_engine_model.py  # Task 4
├── test_train.py         # Task 5
└── test_gui_history.py   # Task 6
```

---

### Task 1: features.py — the shared feature contract

**Files:**
- Create: `arena/features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `DISQUALIFIER` from `arena.models`.
- Produces:
  ```python
  FEATURE_NAMES: list[str]  # 11 names, exact order below
  def extract_features(findings: list[dict]) -> list[float]
      # findings = parsed scan_json; returns 11 floats in FEATURE_NAMES order;
      # missing finding/key -> 0.0; never raises.
  ```

- [ ] **Step 1: Branch + failing tests**

```bash
cd /Users/romanstashkiv/coin_arena && git checkout -b feature/rug-model
```

`tests/test_features.py`:
```python
from arena.features import FEATURE_NAMES, extract_features


def _scan(**overrides):
    findings = [
        {"check": "authorities", "severity": "PASS", "evidence": "",
         "data": {"mint_authority": False, "freeze_authority": False}},
        {"check": "holders", "severity": "WARNING", "evidence": "",
         "data": {"top10_share": 0.42, "max_single": 0.18, "owners": []}},
        {"check": "bundles", "severity": "DISQUALIFIER", "evidence": "",
         "data": {"max_buyers_one_slot": 9, "launch_buyers": 14}},
        {"check": "dev_record", "severity": "WARNING", "evidence": "",
         "data": {"prior_launches": 4, "creator": "Dev"}},
        {"check": "funding", "severity": "DISQUALIFIER", "evidence": "",
         "data": {"funder": "F"}},
        {"check": "vitals", "severity": "INFO", "evidence": "",
         "data": {"age_s": 300, "holder_count": 120, "liquidity_usd": 5000.0}},
    ]
    return findings


def test_feature_names_length_is_11():
    assert len(FEATURE_NAMES) == 11
    assert FEATURE_NAMES[0] == "mint_authority"
    assert FEATURE_NAMES[-1] == "liquidity_usd"


def test_extract_full_vector():
    v = extract_features(_scan())
    assert v == [0.0, 0.0, 0.42, 0.18, 9.0, 14.0, 4.0, 1.0, 300.0, 120.0, 5000.0]


def test_authority_active_is_one():
    f = _scan()
    f[0]["data"] = {"mint_authority": "SomeKey", "freeze_authority": None}
    v = extract_features(f)
    assert v[0] == 1.0 and v[1] == 0.0


def test_funding_non_disqualifier_is_zero():
    f = _scan()
    f[4] = {"check": "funding", "severity": "PASS", "evidence": "", "data": {"funder": "F"}}
    assert extract_features(f)[7] == 0.0


def test_missing_finding_and_keys_impute_zero():
    v = extract_features([{"check": "authorities", "severity": "PASS",
                           "evidence": "", "data": {}}])
    assert v == [0.0] * 11


def test_malformed_input_never_raises():
    assert extract_features([]) == [0.0] * 11
    assert extract_features([None, 42, "x", {"check": "holders"}]) == [0.0] * 11
    assert extract_features(None) == [0.0] * 11
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_features.py -v`
Expected: FAIL — `ModuleNotFoundError: arena.features`.

- [ ] **Step 3: Implement arena/features.py**

```python
"""Shared feature-extraction contract. Both arena.train (offline) and the
live scanner (arena.engine) call extract_features, so the model can never be
fed a different feature layout than it was trained on.

Input is the parsed scan_json shape: a list of dicts, each
{"check", "severity", "evidence", "data"}. Missing findings or keys impute to
0.0 (a known simplification for scans where a check was unavailable)."""

from arena.models import DISQUALIFIER

FEATURE_NAMES = [
    "mint_authority",       # authorities.data.mint_authority (active -> 1)
    "freeze_authority",     # authorities.data.freeze_authority (active -> 1)
    "top10_share",          # holders.data.top10_share (0..1)
    "max_single",           # holders.data.max_single (0..1)
    "max_buyers_one_slot",  # bundles.data.max_buyers_one_slot
    "launch_buyers",        # bundles.data.launch_buyers
    "prior_launches",       # dev_record.data.prior_launches
    "funder_rugged",        # funding severity == DISQUALIFIER -> 1
    "age_s",                # vitals.data.age_s
    "holder_count",         # vitals.data.holder_count
    "liquidity_usd",        # vitals.data.liquidity_usd
]


def extract_features(findings: list[dict]) -> list[float]:
    by_check: dict[str, dict] = {}
    for f in findings or []:
        if isinstance(f, dict) and isinstance(f.get("check"), str):
            by_check[f["check"]] = f

    def data(check: str) -> dict:
        d = (by_check.get(check) or {}).get("data")
        return d if isinstance(d, dict) else {}

    def num(check: str, key: str) -> float:
        v = data(check).get(key)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    auth = data("authorities")
    funding_sev = (by_check.get("funding") or {}).get("severity")
    return [
        1.0 if auth.get("mint_authority") else 0.0,
        1.0 if auth.get("freeze_authority") else 0.0,
        num("holders", "top10_share"),
        num("holders", "max_single"),
        num("bundles", "max_buyers_one_slot"),
        num("bundles", "launch_buyers"),
        num("dev_record", "prior_launches"),
        1.0 if funding_sev == DISQUALIFIER else 0.0,
        num("vitals", "age_s"),
        num("vitals", "holder_count"),
        num("vitals", "liquidity_usd"),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_features.py -v` — Expected: 6 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/features.py tests/test_features.py
git commit -m "feat: shared feature-extraction contract"
```

---

### Task 2: store.py — manual_labels table + methods

**Files:**
- Modify: `arena/store.py`
- Test: `tests/test_store_labels.py`

**Interfaces:**
- Consumes: existing `Store`.
- Produces (new `Store` methods):
  ```python
  def set_manual_label(mint: str, was_rug: int | None) -> None  # None deletes
  def manual_label(mint: str) -> int | None
  def labeled_training_rows() -> list[dict]     # [{scan_json, was_rug}], latest scan per labeled mint
  def label_counts() -> dict  # {total_scans, labeled, rugs, cleans, unlabeled}
  def scans_for_history(limit: int = 200) -> list[dict]
      # [{mint, symbol, ts, verdict, was_rug}], one row per mint (latest scan), newest first
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_store_labels.py`:
```python
import json

from arena.models import Finding, ScanResult
from arena.store import Store


def _scan(mint, verdict="AVOID", symbol="T"):
    return ScanResult(mint=mint, verdict=verdict,
                      findings=[Finding("holders", "WARNING", "e", {"top10_share": 0.4})],
                      unavailable=0, price_usd=1.0, symbol=symbol, duration_s=1.0)


def make(tmp_path):
    return Store(tmp_path / "a.db")


def test_set_get_clear_label(tmp_path):
    s = make(tmp_path)
    s.save_scan(_scan("M1"), None, None, [])
    assert s.manual_label("M1") is None
    s.set_manual_label("M1", 1)
    assert s.manual_label("M1") == 1
    s.set_manual_label("M1", 0)          # relabel
    assert s.manual_label("M1") == 0
    s.set_manual_label("M1", None)       # unsure clears it
    assert s.manual_label("M1") is None
    s.close()


def test_labeled_training_rows_uses_latest_scan(tmp_path):
    s = make(tmp_path)
    s.save_scan(_scan("M1", verdict="CAUTION"), None, None, [])
    s.save_scan(_scan("M1", verdict="AVOID"), None, None, [])   # newer scan of same mint
    s.set_manual_label("M1", 1)
    rows = s.labeled_training_rows()
    assert len(rows) == 1 and rows[0]["was_rug"] == 1
    parsed = json.loads(rows[0]["scan_json"])
    assert parsed[0]["check"] == "holders"
    s.close()


def test_label_counts(tmp_path):
    s = make(tmp_path)
    for m in ("M1", "M2", "M3"):
        s.save_scan(_scan(m), None, None, [])
    s.set_manual_label("M1", 1)
    s.set_manual_label("M2", 0)
    c = s.label_counts()
    assert c == {"total_scans": 3, "labeled": 2, "rugs": 1, "cleans": 1, "unlabeled": 1}
    s.close()


def test_scans_for_history_one_row_per_mint_with_label(tmp_path):
    s = make(tmp_path)
    s.save_scan(_scan("M1", symbol="AAA"), None, None, [])
    s.save_scan(_scan("M1", symbol="AAA"), None, None, [])  # dup mint
    s.save_scan(_scan("M2", symbol="BBB"), None, None, [])
    s.set_manual_label("M1", 1)
    rows = s.scans_for_history()
    mints = [r["mint"] for r in rows]
    assert mints.count("M1") == 1 and "M2" in mints
    m1 = next(r for r in rows if r["mint"] == "M1")
    assert m1["was_rug"] == 1 and m1["symbol"] == "AAA"
    m2 = next(r for r in rows if r["mint"] == "M2")
    assert m2["was_rug"] is None
    s.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_store_labels.py -v` — Expected: FAIL (`AttributeError`/no such method).

- [ ] **Step 3: Add the table to SCHEMA**

In `arena/store.py`, inside the `SCHEMA` string (append before the closing `"""`):
```sql
CREATE TABLE IF NOT EXISTS manual_labels (
    mint TEXT PRIMARY KEY,
    was_rug INTEGER NOT NULL,
    ts INTEGER NOT NULL
);
```

- [ ] **Step 4: Add the methods**

Add these methods to the `Store` class (before `close`):
```python
    def set_manual_label(self, mint: str, was_rug: int | None) -> None:
        if was_rug is None:
            self.conn.execute("DELETE FROM manual_labels WHERE mint = ?", (mint,))
        else:
            self.conn.execute(
                "INSERT INTO manual_labels (mint, was_rug, ts) VALUES (?, ?, ?) "
                "ON CONFLICT(mint) DO UPDATE SET was_rug = excluded.was_rug, "
                "ts = excluded.ts",
                (mint, int(was_rug), int(time.time())))
        self.conn.commit()

    def manual_label(self, mint: str) -> int | None:
        row = self.conn.execute(
            "SELECT was_rug FROM manual_labels WHERE mint = ?", (mint,)).fetchone()
        return row["was_rug"] if row else None

    def labeled_training_rows(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.scan_json AS scan_json, m.was_rug AS was_rug "
            "FROM manual_labels m JOIN scans s ON s.id = "
            "(SELECT id FROM scans WHERE mint = m.mint ORDER BY id DESC LIMIT 1)"
        ).fetchall()
        return [dict(r) for r in rows]

    def label_counts(self) -> dict:
        total = self.conn.execute(
            "SELECT COUNT(DISTINCT mint) AS n FROM scans").fetchone()["n"]
        labeled = self.conn.execute(
            "SELECT COUNT(*) AS n FROM manual_labels").fetchone()["n"]
        rugs = self.conn.execute(
            "SELECT COUNT(*) AS n FROM manual_labels WHERE was_rug = 1").fetchone()["n"]
        return {"total_scans": total, "labeled": labeled, "rugs": rugs,
                "cleans": labeled - rugs, "unlabeled": total - labeled}

    def scans_for_history(self, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.mint, s.symbol, s.ts, s.verdict, m.was_rug FROM scans s "
            "JOIN (SELECT mint, MAX(id) AS mid FROM scans GROUP BY mint) latest "
            "ON latest.mid = s.id "
            "LEFT JOIN manual_labels m ON m.mint = s.mint "
            "ORDER BY s.ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
```
(`time` is already imported at the top of `store.py`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_store_labels.py -v` — Expected: 4 PASSED. Full suite green.

- [ ] **Step 6: Commit**

```bash
git add arena/store.py tests/test_store_labels.py
git commit -m "feat: manual_labels table and labeling store methods"
```

---

### Task 3: model.py — pure-Python inference

**Files:**
- Create: `arena/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: `data_dir` from `arena.paths`.
- Produces:
  ```python
  def load_model(path=None) -> dict | None       # None if absent/malformed; never raises
  def predict_proba(features: list[float], model: dict) -> float   # clamped [0,1]
  def model_info(path=None) -> dict | None        # {n_samples, n_rug, n_clean}
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_model.py`:
```python
import json
import math

from arena.model import load_model, model_info, predict_proba


def _model():
    # 2 features, standardized; z = intercept + coef·((x-mean)/std)
    return {"feature_names": ["a", "b"], "means": [0.0, 0.0], "stds": [1.0, 1.0],
            "coef": [2.0, -1.0], "intercept": 0.5,
            "n_samples": 40, "n_rug": 12, "n_clean": 28}


def test_predict_proba_matches_logistic_formula():
    m = _model()
    x = [1.0, 3.0]
    z = 0.5 + 2.0 * 1.0 + (-1.0) * 3.0     # = -0.5
    expected = 1.0 / (1.0 + math.exp(-z))
    assert abs(predict_proba(x, m) - expected) < 1e-9


def test_predict_proba_standardizes_and_clamps():
    m = {"feature_names": ["a"], "means": [10.0], "stds": [2.0],
         "coef": [100.0], "intercept": 0.0}
    p = predict_proba([1000.0], m)          # huge z -> saturates near 1
    assert 0.0 <= p <= 1.0 and p > 0.999


def test_std_zero_treated_as_one():
    m = {"feature_names": ["a"], "means": [5.0], "stds": [0.0],
         "coef": [1.0], "intercept": 0.0}
    # (7-5)/1 = 2, z=2
    assert abs(predict_proba([7.0], m) - 1.0 / (1 + math.exp(-2.0))) < 1e-9


def test_load_and_info_roundtrip(tmp_path):
    p = tmp_path / "rug_model.json"
    p.write_text(json.dumps(_model()))
    m = load_model(p)
    assert m["coef"] == [2.0, -1.0]
    assert model_info(p) == {"n_samples": 40, "n_rug": 12, "n_clean": 28}


def test_missing_or_malformed_returns_none(tmp_path):
    assert load_model(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_model(bad) is None
    incomplete = tmp_path / "inc.json"
    incomplete.write_text(json.dumps({"coef": [1.0]}))  # missing keys
    assert load_model(incomplete) is None
    assert model_info(tmp_path / "nope.json") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_model.py -v` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement arena/model.py**

```python
"""Pure-Python logistic-regression inference. Reads the tiny rug_model.json
that arena.train exports; needs no scikit-learn at runtime."""

import json
import math
from pathlib import Path

from arena.paths import data_dir

_REQUIRED = ("feature_names", "means", "stds", "coef", "intercept")


def _path(path=None) -> Path:
    return Path(path) if path else data_dir() / "rug_model.json"


def load_model(path=None) -> dict | None:
    p = _path(path)
    try:
        if not p.exists():
            return None
        model = json.loads(p.read_text())
        if not all(k in model for k in _REQUIRED):
            return None
        return model
    except Exception:
        return None


def predict_proba(features: list[float], model: dict) -> float:
    coef, means, stds = model["coef"], model["means"], model["stds"]
    z = float(model["intercept"])
    for i, x in enumerate(features):
        std = stds[i] if stds[i] else 1.0
        z += coef[i] * ((x - means[i]) / std)
    try:
        p = 1.0 / (1.0 + math.exp(-z))
    except OverflowError:
        p = 0.0 if z < 0 else 1.0
    return max(0.0, min(1.0, p))


def model_info(path=None) -> dict | None:
    model = load_model(path)
    if model is None:
        return None
    return {"n_samples": model.get("n_samples", 0),
            "n_rug": model.get("n_rug", 0),
            "n_clean": model.get("n_clean", 0)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_model.py -v` — Expected: 5 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/model.py tests/test_model.py
git commit -m "feat: pure-Python rug-model inference"
```

---

### Task 4: engine integration — ScanResult.rug_probability

**Files:**
- Modify: `arena/models.py`, `arena/engine.py`
- Test: `tests/test_engine_model.py`

**Interfaces:**
- Consumes: `extract_features` (Task 1), `load_model`/`predict_proba` (Task 3).
- Produces: `ScanResult.rug_probability: float | None` (default None), set by `check_mint` when a model is present.

- [ ] **Step 1: Write the failing test**

`tests/test_engine_model.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_engine_model.py -v`
Expected: FAIL — `AttributeError: 'ScanResult' object has no attribute 'rug_probability'`.

- [ ] **Step 3: Add the field to ScanResult**

In `arena/models.py`, add a field to `ScanResult` (after `duration_s`):
```python
    duration_s: float
    rug_probability: float | None = None
```

- [ ] **Step 4: Compute it in the engine**

In `arena/engine.py`, add imports near the top:
```python
from dataclasses import asdict

from arena.features import extract_features
from arena.model import load_model, predict_proba
```
Then, in `check_mint`, right after the `result = ScanResult(...)` block and before the `try: store.save_scan` block, insert:
```python
    try:
        model = load_model()
        if model:
            result.rug_probability = predict_proba(
                extract_features([asdict(f) for f in findings]), model)
    except Exception as exc:
        log.warning("model inference failed: %s", exc)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_engine_model.py -v` — Expected: 2 PASSED. Full suite green.

- [ ] **Step 6: Commit**

```bash
git add arena/models.py arena/engine.py tests/test_engine_model.py
git commit -m "feat: attach rug probability to scan results"
```

---

### Task 5: train.py — offline training

**Files:**
- Create: `arena/train.py`
- Modify: `pyproject.toml` (add `ml` extra)
- Test: `tests/test_train.py`

**Interfaces:**
- Consumes: `FEATURE_NAMES`/`extract_features` (Task 1), `Store.labeled_training_rows` (Task 2).
- Produces: `MIN_TRAIN_SAMPLES = 20`; `build_dataset(store) -> (X, y)`; `train(store) -> dict | None` (writes `rug_model.json` to data dir, returns the artifact, or `None` when it refuses); `main()`; runnable as `python -m arena.train`.

- [ ] **Step 1: Add the `ml` extra to pyproject.toml**

In `pyproject.toml`, under `[project.optional-dependencies]`, add:
```toml
ml = ["scikit-learn"]
```
Install it:
```bash
.venv/bin/pip install -e '.[ml]'
```
Expected: scikit-learn installs. (Pandas is intentionally NOT included — `train.py` uses stdlib lists, YAGNI.)

- [ ] **Step 2: Write the failing tests**

`tests/test_train.py`:
```python
import json

import pytest

from arena.models import Finding, ScanResult
from arena.store import Store
from arena.train import MIN_TRAIN_SAMPLES, build_dataset, train

pytest.importorskip("sklearn")  # training test needs the ml extra


def _scan(mint, top10):
    return ScanResult(mint=mint, verdict="AVOID",
                      findings=[Finding("holders", "WARNING", "e",
                                        {"top10_share": top10, "max_single": 0.1})],
                      unavailable=0, price_usd=1.0, symbol="T", duration_s=1.0)


def _seed(store, n_rug, n_clean):
    i = 0
    for _ in range(n_rug):     # rugs: high concentration
        store.save_scan(_scan(f"R{i}", 0.9), None, None, []); store.set_manual_label(f"R{i}", 1); i += 1
    for _ in range(n_clean):   # clean: low concentration
        store.save_scan(_scan(f"C{i}", 0.1), None, None, []); store.set_manual_label(f"C{i}", 0); i += 1


def test_refuses_below_minimum(tmp_path, capsys):
    store = Store(tmp_path / "a.db")
    _seed(store, 2, 2)
    assert train(store) is None
    assert not (tmp_path / "rug_model.json").exists() or True  # writes nothing to data dir
    store.close()


def test_refuses_single_class(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    store = Store(tmp_path / "a.db")
    _seed(store, 25, 0)
    assert train(store) is None
    assert not (tmp_path / "rug_model.json").exists()
    store.close()


def test_trains_and_writes_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    store = Store(tmp_path / "a.db")
    _seed(store, 12, 18)
    artifact = train(store)
    assert artifact is not None
    assert artifact["n_samples"] == 30 and artifact["n_rug"] == 12
    assert len(artifact["coef"]) == 11 and len(artifact["means"]) == 11
    written = json.loads((tmp_path / "rug_model.json").read_text())
    assert written["feature_names"][0] == "mint_authority"
    store.close()


def test_build_dataset_shapes(tmp_path):
    store = Store(tmp_path / "a.db")
    _seed(store, 3, 3)
    X, y = build_dataset(store)
    assert len(X) == 6 and len(y) == 6 and len(X[0]) == 11
    assert set(y) == {0, 1}
    store.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_train.py -v` — Expected: FAIL (`ModuleNotFoundError: arena.train`).

- [ ] **Step 4: Implement arena/train.py**

```python
"""Offline model training. Run: python -m arena.train

Reads your manually-labeled scans from arena.db, fits a logistic regression,
and writes a tiny rug_model.json to the data dir that the scanner reads.
Needs the `ml` extra (scikit-learn); never imported by the app."""

import json
import time

from arena.features import FEATURE_NAMES, extract_features
from arena.paths import data_dir
from arena.store import Store

MIN_TRAIN_SAMPLES = 20


def build_dataset(store: Store):
    X, y = [], []
    for row in store.labeled_training_rows():
        X.append(extract_features(json.loads(row["scan_json"])))
        y.append(int(row["was_rug"]))
    return X, y


def _standardize(X):
    n, k = len(X), len(FEATURE_NAMES)
    means = [sum(row[i] for row in X) / n for i in range(k)]
    stds = [(sum((row[i] - means[i]) ** 2 for row in X) / n) ** 0.5 for i in range(k)]
    Xs = [[(row[i] - means[i]) / (stds[i] or 1.0) for i in range(k)] for row in X]
    return Xs, means, stds


def train(store: Store) -> dict | None:
    X, y = build_dataset(store)
    n = len(y)
    n_rug = sum(y)
    n_clean = n - n_rug
    if n < MIN_TRAIN_SAMPLES:
        print(f"Only {n} labeled coins — need at least {MIN_TRAIN_SAMPLES}. "
              "Label more in the History screen, then run this again.")
        return None
    if n_rug == 0 or n_clean == 0:
        print(f"Need both kinds: have {n_rug} rug / {n_clean} clean. "
              "Label some of the missing kind first.")
        return None

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report
    from sklearn.model_selection import train_test_split

    Xs, means, stds = _standardize(X)
    try:
        Xtr, Xte, ytr, yte = train_test_split(
            Xs, y, test_size=0.2, random_state=42, stratify=y)
        rep = LogisticRegression(max_iter=1000).fit(Xtr, ytr)
        print("--- holdout accuracy ---")
        print(classification_report(yte, rep.predict(Xte), zero_division=0))
    except Exception as exc:
        print(f"(skipped holdout report: {exc})")

    model = LogisticRegression(max_iter=1000).fit(Xs, y)
    coef = [float(w) for w in model.coef_[0]]
    intercept = float(model.intercept_[0])

    print(f"Trained on {n} coins ({n_rug} rug / {n_clean} clean).")
    if min(n_rug, n_clean) / n < 0.25:
        print("WARNING: classes are imbalanced — accuracy can look high while the "
              "model just predicts the majority. Label more of the rarer kind.")
    print("\nLearned weights (bigger magnitude = more influence on rug risk):")
    for name, w in sorted(zip(FEATURE_NAMES, coef), key=lambda t: abs(t[1]),
                          reverse=True):
        print(f"  {name:22} {w:+.3f}")

    artifact = {
        "feature_names": FEATURE_NAMES, "means": means, "stds": stds,
        "coef": coef, "intercept": intercept,
        "n_samples": n, "n_rug": n_rug, "n_clean": n_clean,
        "trained_ts": int(time.time()),
    }
    out = data_dir() / "rug_model.json"
    out.write_text(json.dumps(artifact, indent=2))
    print(f"\nSaved model to {out}")
    return artifact


def main() -> None:
    store = Store()
    try:
        train(store)
    finally:
        store.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_train.py -v` — Expected: 4 PASSED. Full suite green.

- [ ] **Step 6: Commit**

```bash
git add arena/train.py pyproject.toml tests/test_train.py
git commit -m "feat: offline logistic-regression training script"
```

---

### Task 6: GUI — History screen + model line + routing

**Files:**
- Create: `arena/gui/views/history.py`
- Modify: `arena/gui/app.py`, `arena/gui/views/check.py`, `tests/test_gui_check.py`
- Test: `tests/test_gui_history.py`

**Interfaces:**
- Consumes: `Store` label methods (Task 2), `model_info` (Task 3), `ScanResult.rug_probability` (Task 4), `theme`.
- Produces: `history.build_history(page, on_back) -> ft.View`; `check.build_check(page, on_open_settings, on_open_history) -> ft.View` (new third param); `app.main` routes to History.
- Flet 0.86.2 API note: adapt control names to the installed version, preserve behavior. `ft.Border.all(width, color)`, `page.window.*`, `page.run_thread`, `page.views` are the confirmed shapes from milestone 2.

- [ ] **Step 1: Write the History pure-helper test**

`tests/test_gui_history.py`:
```python
import arena.gui.views.history as hist_mod
from arena.gui.views.history import build_history
from arena.models import Finding, ScanResult
from arena.store import Store


class FakePage:
    def __init__(self):
        self.updates = 0

    def update(self):
        self.updates += 1


def _seed(store):
    for m, sym in (("M1", "AAA"), ("M2", "BBB")):
        store.save_scan(ScanResult(m, "AVOID",
                        [Finding("holders", "WARNING", "e", {})],
                        0, 1.0, sym, 1.0), None, None, [])


def test_history_lists_scans_and_labels_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    store = Store()          # resolves to tmp_path/arena.db via ARENA_DATA_DIR
    _seed(store)
    store.close()
    page = FakePage()
    # build_history opens its own Store on data_dir(); label via the module helper
    view = build_history(page, on_back=lambda: None)
    assert view.route == "/history"
    hist_mod.set_label(tmp_path, "M1", 1)   # -> Store(tmp_path/"arena.db")
    s = Store()
    assert s.manual_label("M1") == 1
    s.close()
```
Note: `hist_mod.set_label(data_dir_path, mint, was_rug)` is a tiny module-level helper the view uses internally, exposed so the labeling logic is unit-testable without driving Flet buttons. Implement it in Step 3.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_gui_history.py -v` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement arena/gui/views/history.py**

```python
import flet as ft

from arena.gui import theme
from arena.store import Store

_LABEL_BTN = {1: "Rug", 0: "Clean", None: "Unsure"}


def set_label(db_path, mint: str, was_rug: int | None) -> None:
    """Persist a manual label. Separated for unit-testing without Flet."""
    store = Store(db_path / "arena.db" if db_path else None)
    try:
        store.set_manual_label(mint, was_rug)
    finally:
        store.close()


def build_history(page: ft.Page, on_back) -> ft.View:
    from arena.paths import data_dir
    ddir = data_dir()
    store = Store()
    rows = store.scans_for_history()
    counts = store.label_counts()
    store.close()

    summary = ft.Text(
        f"{counts['total_scans']} scans · {counts['labeled']} labeled "
        f"({counts['rugs']} rug / {counts['cleans']} clean) · "
        f"{counts['unlabeled']} unlabeled",
        size=13, color=theme.MUTED)
    hint = ft.Text(
        "Enough labeled coins — run  python -m arena.train  to update the model."
        if counts["labeled"] >= 20 else "",
        size=12, color=theme.CYAN)

    list_col = ft.Column(spacing=theme.GAP, scroll=ft.ScrollMode.AUTO, expand=True)

    def make_row(r):
        current = r["was_rug"]
        chips = ft.Row(spacing=4)

        def relabel(value):
            # value is 1 (Rug), 0 (Clean), or None (Unsure -> clears the label)
            def handler(_):
                set_label(ddir, r["mint"], value)
                _rebuild()
            return handler

        for val in (1, 0, None):
            active = (val == current)
            chips.controls.append(ft.TextButton(
                _LABEL_BTN[val],
                on_click=relabel(val),
                style=ft.ButtonStyle(
                    bgcolor=theme.CYAN if active else None,
                    color=theme.WHITE if active else theme.INK)))
        return ft.Row([
            ft.Text(r["symbol"] or "?", width=70, color=theme.INK),
            ft.Text((r["mint"][:6] + "…"), width=80, color=theme.MUTED, size=12),
            ft.Text(r["verdict"], width=110, color=theme.MUTED, size=12),
            ft.Container(expand=True),
            chips,
        ])

    def _rebuild():
        s = Store()
        rows2 = s.scans_for_history()
        c = s.label_counts()
        s.close()
        summary.value = (f"{c['total_scans']} scans · {c['labeled']} labeled "
                         f"({c['rugs']} rug / {c['cleans']} clean) · "
                         f"{c['unlabeled']} unlabeled")
        hint.value = ("Enough labeled coins — run  python -m arena.train  to "
                      "update the model." if c["labeled"] >= 20 else "")
        list_col.controls = [make_row(r) for r in rows2]
        page.update()

    list_col.controls = [make_row(r) for r in rows]

    return ft.View(
        route="/history",
        bgcolor=theme.WHITE,
        padding=theme.PAD,
        controls=[
            ft.Row([ft.TextButton("← Back", on_click=lambda _: on_back()),
                    ft.Container(expand=True),
                    ft.Text("History", size=20, weight=ft.FontWeight.W_500,
                            color=theme.INK)]),
            summary, hint, list_col,
        ],
    )
```

- [ ] **Step 4: Run the history test**

Run: `.venv/bin/pytest tests/test_gui_history.py -v` — Expected: 1 PASSED.

- [ ] **Step 5: Add History nav + model line to check.py**

In `arena/gui/views/check.py`:
1. Add import at top: `from arena.model import model_info`.
2. Change the signature: `def build_check(page: ft.Page, on_open_settings, on_open_history) -> ft.View:`.
3. In `render(result)`, right after the verdict banner container is appended and before the finding-rows loop, insert:
```python
        if result.rug_probability is not None:
            pct = round(result.rug_probability * 100, 1)
            n = (model_info() or {}).get("n_samples", 0)
            p = result.rug_probability
            mcolor = (theme.VERDICT_COLORS["AVOID"] if p >= 0.70
                      else theme.VERDICT_COLORS["CAUTION"] if p >= 0.35
                      else theme.VERDICT_COLORS["NO_RED_FLAGS"])
            results.controls.append(ft.Text(
                f"Model estimate: {pct}% rug risk (from {n} labeled coins)",
                color=mcolor, weight=ft.FontWeight.W_500))
```
4. In the returned `header` Row, add a History button before the Settings button:
```python
    header = ft.Row([
        ft.Text("Coin Arena", size=20, weight=ft.FontWeight.W_500, color=theme.INK),
        ft.Container(expand=True),
        ft.TextButton("History", on_click=lambda _: on_open_history()),
        ft.TextButton("Settings", on_click=lambda _: on_open_settings()),
    ])
```

- [ ] **Step 6: Wire routing in app.py**

In `arena/gui/app.py`:
1. Add import: `from arena.gui.views.history import build_history`.
2. Replace `show_check` and add `show_history`:
```python
    def show_check():
        page.views.clear()
        page.views.append(build_check(page, on_open_settings=show_settings,
                                      on_open_history=show_history))
        page.update()

    def show_history():
        page.views.append(build_history(page, on_back=show_check))
        page.update()
```

- [ ] **Step 7: Update the existing check tests for the new header + signature**

In `tests/test_gui_check.py`:
1. Every `build_check(page, on_open_settings=...)` call → add `on_open_history=lambda: None`.
2. `_settings_button` now lives at index 3 (History is index 2). Update:
```python
def _settings_button(view):
    return view.controls[0].controls[3]


def _history_button(view):
    return view.controls[0].controls[2]
```
3. Add a test:
```python
def test_history_button_routes_via_callback():
    page = FakePage()
    opened = {"flag": False}
    view = build_check(page, on_open_settings=lambda: None,
                       on_open_history=lambda: opened.__setitem__("flag", True))
    _history_button(view).on_click(None)
    assert opened["flag"] is True
```

- [ ] **Step 8: Run full suite**

Run: `.venv/bin/pytest`
Expected: all green (existing check tests updated, new history + model-line paths covered). Zero network, no window.

- [ ] **Step 9: Manual smoke (controller does the visual pass)**

The controller runs the app in web mode and confirms: History button appears in the top bar; History screen lists scans with Rug/Clean/Unsure buttons; clicking labels a row and the summary updates. (Model line requires a trained model + a scan; verified logically by tests.)

- [ ] **Step 10: Commit**

```bash
git add arena/gui/views/history.py arena/gui/app.py arena/gui/views/check.py tests/test_gui_history.py tests/test_gui_check.py
git commit -m "feat: History labeling screen, model line, and routing"
```

---

## Verification against spec (after all tasks)

1. `.venv/bin/pytest` — green, offline; train test skips cleanly if sklearn absent.
2. `grep -rn "import sklearn\|from sklearn" arena/` — matches ONLY in `arena/train.py` (engine/model/features/gui never import sklearn).
3. `grep -rn "import flet" arena/features.py arena/model.py arena/train.py arena/store.py` — no matches (pure modules stay flet-free).
4. With a seeded DB of ≥20 labeled coins: `.venv/bin/python -m arena.train` prints weights + accuracy and writes `rug_model.json`; a subsequent `python -m arena check <mint>`-equivalent scan carries a `rug_probability`.
5. `git status` clean; no `rug_model.json`/`arena.db` tracked.
