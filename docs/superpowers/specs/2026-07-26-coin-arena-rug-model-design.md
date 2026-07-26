# Coin Arena Rug Model — Design Spec (Milestone 3)

**Date:** 2026-07-26
**Status:** Approved in brainstorm; pending user review of this document
**Builds on:** Milestone 1 (engine + CLI) and Milestone 2 (GUI), both on main.

## Purpose

Let the user manually label past scans as rug / clean, train a logistic-
regression model offline on those labels, and have the scanner display a
rug-probability alongside the existing rules verdict — replacing hand-picked
thresholds with weights learned from the user's own data. Everything is
manual and on-demand: nothing runs in the background.

## Key decisions (made with user)

| Decision | Choice |
|---|---|
| Labeling UI | New **History** screen in the GUI: list of past scans, each with Rug / Clean / Unsure buttons |
| Risk display | Show **both** — keep the 🔴/🟡/🟢 rules verdict, and ADD a "Model estimate: N% rug risk" line when a trained model exists |
| Training | Terminal command `python -m arena.train`, run on demand from source; needs scikit-learn (dev-only extra), never bundled in the app |
| Inference | Pure-Python in the engine (stdlib `math`), reads a tiny `rug_model.json`; zero new runtime deps |
| Labels | Manual labels are the training source of truth, stored separately from the automated `verify` outcomes |
| Constraint | No background processes; training and labeling are both user-initiated |

## Architecture

The heavy library (scikit-learn) lives only in training, run offline. The app
does featherweight inference. Training writes a ~1 KB `rug_model.json` into the
shared data dir (`~/Library/Application Support/CoinArena/`); the app (source or
packaged) reads it on the next scan.

New/changed files:
```
arena/
├── features.py          # NEW — extract_features(): shared train/infer contract
├── model.py             # NEW — pure-Python inference (load + predict_proba)
├── train.py             # NEW — python -m arena.train (sklearn, offline)
├── store.py             # MODIFY — manual_labels table + methods
├── models.py            # MODIFY — ScanResult gains rug_probability
├── engine.py            # MODIFY — compute + attach rug_probability per scan
└── gui/
    ├── app.py           # MODIFY — route to History
    ├── views/
    │   ├── check.py     # MODIFY — History nav button + model line
    │   └── history.py   # NEW — labeling worklist
```

New dependency: `scikit-learn` + `pandas` in a new `ml` optional-extra
(`pip install -e '.[ml]'`), used only by `train.py`. The `gui` extra is
unchanged, so the packaged app stays lean.

## Database

One new table (added to `store.py`'s `SCHEMA`):
```sql
CREATE TABLE IF NOT EXISTS manual_labels (
    mint TEXT PRIMARY KEY,
    was_rug INTEGER NOT NULL,   -- 1 = rug, 0 = clean
    ts INTEGER NOT NULL
);
```
Kept separate from `coin_outcomes` (the automated `verify` results) so the
user's judgment is authoritative and unambiguous for training.

New `Store` methods:
- `set_manual_label(mint: str, was_rug: int | None) -> None` — upsert; `None`
  deletes the row (the "Unsure" action → excluded from training).
- `manual_label(mint: str) -> int | None` — current label or None.
- `labeled_training_rows() -> list[dict]` — one row per labeled mint:
  `{scan_json, was_rug}`, using that mint's most recent scan's `scan_json`.
- `label_counts() -> dict` — `{total_scans, labeled, rugs, cleans, unlabeled}`.
- `scans_for_history(limit=200) -> list[dict]` — `{mint, symbol, ts, verdict,
  was_rug}` newest first (LEFT JOIN manual_labels), for the History screen.

## Feature extraction (`features.py`) — the shared contract

`FEATURE_NAMES` is a fixed, ordered list. `extract_features(findings) ->
list[float]` (findings = the parsed `scan_json` list) returns values in that
exact order. Both `train.py` and the engine call it, so features can never
drift. Missing values (a check that returned INFO "unavailable") impute to 0.

| # | FEATURE_NAMES entry | Source finding.data (or severity) |
|---|---|---|
| 0 | `mint_authority` | authorities.data["mint_authority"] → 1/0 |
| 1 | `freeze_authority` | authorities.data["freeze_authority"] → 1/0 |
| 2 | `top10_share` | holders.data["top10_share"] (0..1) |
| 3 | `max_single` | holders.data["max_single"] (0..1) |
| 4 | `max_buyers_one_slot` | bundles.data["max_buyers_one_slot"] |
| 5 | `launch_buyers` | bundles.data["launch_buyers"] |
| 6 | `prior_launches` | dev_record.data["prior_launches"] |
| 7 | `funder_rugged` | funding severity == DISQUALIFIER → 1 else 0 |
| 8 | `age_s` | vitals.data["age_s"] (0 if None) |
| 9 | `holder_count` | vitals.data["holder_count"] (0 if None) |
| 10 | `liquidity_usd` | vitals.data["liquidity_usd"] (0 if None) |

`extract_features` is robust: a finding absent from a scan, or a `data` dict
missing a key, yields 0 for that feature (never raises).

## Model artifact (`rug_model.json`)

Written by `train.py` to `data_dir()/"rug_model.json"`:
```json
{
  "feature_names": ["mint_authority", ...],
  "means":  [...],   "stds": [...],     // per-feature standardization
  "coef":   [...],   "intercept": 0.0,  // fitted logistic weights
  "n_samples": 41, "n_rug": 12, "n_clean": 29, "trained_ts": 1753...
}
```

## Training (`arena/train.py`, `python -m arena.train`)

1. Open `Store`, read `labeled_training_rows()`.
2. Build `X` via `features.extract_features` (parse each `scan_json`), `y` from
   `was_rug`.
3. **Guards** (refuse and print guidance, write nothing):
   - fewer than `MIN_TRAIN_SAMPLES = 20` labeled rows, or
   - only one class present (all rug or all clean).
4. Standardize `X` (mean/std per feature; std 0 → treated as 1). Fit
   `sklearn.linear_model.LogisticRegression`.
5. Print: sample count, class balance (n_rug / n_clean), accuracy from a
   train/test split, and each feature's learned weight (sorted by magnitude —
   the interesting part). Loudly note class imbalance if one class < 25%.
6. Write `rug_model.json`. No `.pkl`, no joblib — the JSON is the artifact.

Console-only; no files besides `rug_model.json`; exits cleanly.

## Inference (`arena/model.py`, pure Python)

- `load_model(path=None) -> dict | None` — reads `rug_model.json` from the data
  dir; `None` if absent or malformed (never raises).
- `predict_proba(features: list[float], model: dict) -> float` — standardize
  with stored means/stds, `z = intercept + Σ coef_i · x_i'`, return
  `1/(1+exp(-z))`, clamped to [0,1].
- `model_info(path=None) -> dict | None` — `{n_samples, n_rug, n_clean}` for the
  UI's "(from N labeled coins)" note.

`engine.check_mint`: after building `findings`, if a model loads, compute
`extract_features(findings)` → `predict_proba` and set
`result.rug_probability` (else leave it `None`). Wrapped so a model error can
never break a scan — a bad model just means no probability line.

`ScanResult` gains `rug_probability: float | None = None`.

## GUI

**Check screen (`check.py`):** add a **"History"** text button in the top bar
(next to Settings). When `result.rug_probability is not None`, render one line
under the verdict banner: **"Model estimate: {pct}% rug risk (from {N} labeled
coins)"**, colored by band (≥70 red / ≥35 amber / else green) — but the
existing rules verdict banner and six finding rows are unchanged. No model →
no line.

**History screen (`history.py`):** `build_history(page, on_back)`.
- Top summary from `label_counts()`: "18 scans · 11 labeled (4 rug / 7 clean)
  · 7 unlabeled", plus a hint shown only when `labeled >= MIN_TRAIN_SAMPLES`
  (20, the same threshold `train.py` enforces): "Enough labeled coins — run
  `python -m arena.train` to update the model."
- Scrollable list from `scans_for_history()`; each row: symbol, truncated
  mint, date, verdict, and **Rug / Clean / Unsure** buttons. The active label
  is highlighted. Clicking calls `set_manual_label` and refreshes the row +
  summary. Back → Check.

**Routing (`app.py`):** `show_history()` pushes the History view; its Back
returns to Check.

## Error handling

- Missing/malformed `rug_model.json` → inference silently returns no
  probability; app and rules verdict unaffected.
- `extract_features` never raises (missing findings/keys → 0).
- `train.py` refuses on too little / single-class data with a clear message;
  never writes a garbage model.
- Labeling writes are immediate and isolated; a DB error surfaces inline on
  the History screen, never crashes.

## Honest ML guardrails (built in, not just documented)

- The model line always shows the sample count, so a toy model reads as a toy.
- The rules verdict stays as the always-present baseline; the model augments,
  never replaces it.
- `train.py` prints class balance and accuracy so the "always predict the
  majority class" trap is visible (94% accuracy on 30-clean/2-rug is exposed,
  not hidden).
- Missing-value→0 imputation is a known simplification, documented in
  `features.py`.

## Testing

- `features.py` — unit tests: a fixture `scan_json` → the exact 11-value
  vector, including the absent-finding and missing-key → 0 paths.
- `model.py` — unit tests: a hand-written `rug_model.json` + a feature vector →
  a probability verified by hand against the logistic formula; malformed/absent
  model → None.
- `store.py` — unit tests: set/clear manual labels, relabel, `label_counts`,
  `labeled_training_rows` (latest-scan-per-mint), `scans_for_history`.
- `train.py` — test against a small synthetic labeled dataset: writes a valid
  `rug_model.json` with all expected keys; refuses on <20 rows and on
  single-class. Marked as needing the `ml` extra.
- `engine.py` — test that a scan with a present model attaches a
  `rug_probability`, and one without a model leaves it `None`.
- GUI History — thin; manual smoke (label a row, see summary update).
- Default `pytest` stays offline; sklearn-dependent train test guarded/skipped
  if sklearn absent.

## Out of scope (fast-follow / later)

- Random forest / XGBoost (logistic regression first — interpretable, tiny).
- Automated labeling (deliberately manual per user).
- Model versioning / history of past models.
- Retraining from inside the app (stays a terminal command to keep the app lean).
- Feature engineering beyond the 11 raw values (interactions, ratios).
