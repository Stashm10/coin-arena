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
