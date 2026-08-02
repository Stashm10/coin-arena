import arena.gui.views.sizing as sizing_mod
from arena.flow.kelly import KellyResult
from arena.flow.tips import TipFloor
from arena.gui.views.sizing import build_sizing


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _fields(view):
    return view.controls[1].controls[:5]


def _compute_button(view):
    return view.controls[1].controls[5].controls[0]


def _tips_button(view):
    return view.controls[1].controls[5].controls[1]


def _out(view):
    return view.controls[1].controls[6]


def _texts(view):
    return [c.value for c in _out(view).controls if hasattr(c, "value")]


def test_route_is_sizing():
    assert build_sizing(FakePage(), on_back=lambda: None).route == "/sizing"


def test_back_button_routes():
    clicked = {"flag": False}
    view = build_sizing(FakePage(),
                        on_back=lambda: clicked.__setitem__("flag", True))
    view.controls[0].controls[0].on_click(None)
    assert clicked["flag"] is True


def test_five_belief_inputs_have_defaults():
    view = build_sizing(FakePage(), on_back=lambda: None)
    assert len(_fields(view)) == 5
    assert all(f.value for f in _fields(view))


def test_compute_renders_fraction_and_sensitivity(monkeypatch):
    result = KellyResult(f_star=0.12, f_constrained=0.05, drawdown_prob=0.03,
                         sensitivity=[("half hit rate", 0.01),
                                      ("stated hit rate", 0.05),
                                      ("double hit rate", 0.14)])
    monkeypatch.setattr(sizing_mod, "run_kelly",
                        lambda inputs, on_done, on_error: on_done(result))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _compute_button(view).on_click(None)
    text = " ".join(_texts(view))
    assert "5.0%" in text            # f_constrained as a percentage
    assert "half hit rate" in text   # the sensitivity table is the point
    assert "double hit rate" in text


def test_compute_labels_the_numbers_as_beliefs(monkeypatch):
    result = KellyResult(0.1, 0.05, 0.02,
                         [("half hit rate", 0.01), ("stated hit rate", 0.05),
                          ("double hit rate", 0.1)])
    monkeypatch.setattr(sizing_mod, "run_kelly",
                        lambda inputs, on_done, on_error: on_done(result))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _compute_button(view).on_click(None)
    assert any("assumption" in t.lower() or "belief" in t.lower()
               for t in _texts(view))


def test_invalid_input_shows_an_error_without_computing(monkeypatch):
    called = {"flag": False}
    monkeypatch.setattr(sizing_mod, "run_kelly",
                        lambda **kw: called.__setitem__("flag", True))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _fields(view)[0].value = "not a number"
    _compute_button(view).on_click(None)
    assert called["flag"] is False
    assert any("number" in t.lower() for t in _texts(view))


def test_tips_button_renders_percentiles(monkeypatch):
    tips = TipFloor(p25=1e-6, p50=1e-6, p75=1.6e-6, p95=5e-4, p99=1.85e-3)
    monkeypatch.setattr(sizing_mod, "run_tips",
                        lambda on_done, on_error: on_done(tips))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _tips_button(view).on_click(None)
    text = " ".join(_texts(view))
    assert "0.0005" in text or "5.0e-04" in text.lower()
    assert "recommend" in text.lower()


def test_tips_failure_is_shown(monkeypatch):
    monkeypatch.setattr(sizing_mod, "run_tips",
                        lambda on_done, on_error: on_error(RuntimeError("down")))
    view = build_sizing(FakePage(), on_back=lambda: None)
    _tips_button(view).on_click(None)
    assert any("tips unavailable" in t.lower() for t in _texts(view))
