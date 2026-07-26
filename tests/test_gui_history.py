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
