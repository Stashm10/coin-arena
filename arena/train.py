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
