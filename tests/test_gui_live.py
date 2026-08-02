import arena.gui.views.live as live_mod
from arena.flow.signal import DISCONNECTED, EXIT, HEATING
from arena.flow.signal import SignalState
from arena.gui.views.live import build_live


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _input_row(view):
    return view.controls[1].controls[0]


def _readout(view):
    return view.controls[1].controls[1]


def _sensitivity(view):
    return view.controls[0].controls[3]


def test_route_is_live():
    assert build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None).route == "/live"


def test_back_button_routes():
    clicked = {"flag": False}
    view = build_live(FakePage(),
                      on_back=lambda: clicked.__setitem__("flag", True),
                      on_open_sizing=lambda: None)
    view.controls[0].controls[0].on_click(None)
    assert clicked["flag"] is True


def test_sizing_button_routes():
    clicked = {"flag": False}
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: clicked.__setitem__("flag", True))
    view.controls[0].controls[4].on_click(None)
    assert clicked["flag"] is True


def test_invalid_mint_shows_error_without_starting_a_watch(monkeypatch):
    started = {"flag": False}
    monkeypatch.setattr(live_mod, "start_watch",
                        lambda **kw: started.__setitem__("flag", True))
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    _input_row(view).controls[0].value = "notamint"
    _input_row(view).controls[1].on_click(None)
    assert started["flag"] is False
    assert "not a valid" in _readout(view).controls[0].value


def test_missing_key_explains_instead_of_watching(monkeypatch):
    started = {"flag": False}
    monkeypatch.setattr(live_mod, "start_watch",
                        lambda **kw: started.__setitem__("flag", True))
    monkeypatch.setattr(live_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": None})())
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    _input_row(view).controls[0].value = "M" * 44
    _input_row(view).controls[1].on_click(None)
    assert started["flag"] is False
    assert "Helius key" in _readout(view).controls[0].value


def test_disconnected_state_hides_numbers_and_warns():
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    live_mod.render_state(view, SignalState(DISCONNECTED, None, None, None,
                                            None, None, "socket disconnected"))
    text = " ".join(c.value for c in _readout(view).controls if hasattr(c, "value"))
    assert "DISCONNECTED" in text
    assert "not" in text.lower()  # e.g. "signal is not live"
    assert "η" not in text


def test_hazard_is_labelled_as_assumed():
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    live_mod.render_state(view, SignalState(HEATING, 0.7, 0.8, 4.0, 5.0,
                                            0.001, "cascade alive"))
    text = " ".join(c.value for c in _readout(view).controls if hasattr(c, "value"))
    assert "assumed" in text.lower()


def test_sensitivity_dropdown_offers_three_presets():
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    values = [o.key for o in _sensitivity(view).options]
    assert values == ["early", "balanced", "late"]
    assert _sensitivity(view).value == "balanced"
