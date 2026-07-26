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
