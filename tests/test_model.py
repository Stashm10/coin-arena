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
