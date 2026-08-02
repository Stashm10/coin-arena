import arena.gui.views.live as live_mod
from arena.flow.signal import DISCONNECTED, EXIT, HEATING, SignalEngine
from arena.flow.signal import SignalState
from arena.gui.views.live import build_live
from arena.thresholds import (QME_HAZARD_MULT_CONCENTRATED,
                              QME_HAZARD_MULT_CREATOR_SELLING,
                              QME_HAZARD_MULT_MINT_LIVE)


def _collapsing_points(n=25, price=10.0):
    return [(float(i), price * (0.9 ** i)) for i in range(n)]


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


class FakeHandle:
    def stop(self) -> None:
        pass


def _input_row(view):
    return view.controls[1].controls[0]


def _toggles(view):
    # Body column: [input row, hazard toggles row, readout column].
    return view.controls[1].controls[1]


def _readout(view):
    return view.controls[1].controls[2]


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


def test_render_state_does_not_crash_when_eta_is_set_but_peak_is_none():
    # Defensive: render_state must degrade gracefully, never raise, on a
    # state with eta/lam set but eta_peak/lam_peak None. The engine should
    # no longer emit this in practice (see test_flow_signal.py's
    # test_latched_state_backfills_peaks_once_a_fit_becomes_available), but
    # this render callback runs on every tick during EXIT and must not be
    # able to take the window down if it ever does.
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    live_mod.render_state(view, SignalState(EXIT, 0.71, None, 10.2, None,
                                            -0.1, "hazard exceeds drift"))
    text = " ".join(c.value for c in _readout(view).controls if hasattr(c, "value"))
    assert "EXIT" in text


def test_latched_growth_past_min_fit_events_renders_without_crashing():
    # Full-stack regression: fast-rug latch under MIN_FIT_EVENTS (peaks
    # None), then continued trading past MIN_FIT_EVENTS while still
    # latched. eta/lam become numbers once a fit succeeds; rendering the
    # resulting state must not raise.
    eng = SignalEngine()
    few_times = [float(i) for i in range(25)]
    latched = eng.update(now=24.0, times=few_times,
                         price_points=_collapsing_points(n=25),
                         hazard_ps=0.001)
    assert latched.state == EXIT

    many_times = [float(i) for i in range(50)]
    grown = eng.update(now=49.0, times=many_times,
                       price_points=_collapsing_points(n=50), hazard_ps=0.001)
    assert grown.state == EXIT
    assert grown.eta is not None

    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    live_mod.render_state(view, grown)  # must not raise


def test_toggling_checkbox_changes_multipliers_passed_to_start_watch(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        live_mod, "start_watch",
        lambda **kw: (captured.setdefault("get_multipliers",
                                          kw.get("get_multipliers")),
                     FakeHandle())[1])
    monkeypatch.setattr(live_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": "k"})())
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    _input_row(view).controls[0].value = "M" * 44
    _toggles(view).controls[0].value = True  # mint authority still live
    _input_row(view).controls[1].on_click(None)
    get_multipliers = captured["get_multipliers"]
    assert get_multipliers() == [QME_HAZARD_MULT_MINT_LIVE]


def test_no_toggles_ticked_passes_no_multipliers(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        live_mod, "start_watch",
        lambda **kw: (captured.setdefault("get_multipliers",
                                          kw.get("get_multipliers")),
                     FakeHandle())[1])
    monkeypatch.setattr(live_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": "k"})())
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    _input_row(view).controls[0].value = "M" * 44
    _input_row(view).controls[1].on_click(None)
    get_multipliers = captured["get_multipliers"]
    assert get_multipliers() == []


def test_hazard_readout_shows_active_multiplier_labels_and_stays_assumed(
        monkeypatch):
    captured = {}
    monkeypatch.setattr(
        live_mod, "start_watch",
        lambda **kw: (captured.setdefault("on_state", kw["on_state"]),
                     FakeHandle())[1])
    monkeypatch.setattr(live_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": "k"})())
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    _input_row(view).controls[0].value = "M" * 44
    _toggles(view).controls[0].value = True  # mint authority still live
    _toggles(view).controls[2].value = True  # creator wallet selling
    _input_row(view).controls[1].on_click(None)
    on_state = captured["on_state"]
    on_state(SignalState(HEATING, 0.7, 0.8, 4.0, 5.0, 0.001, "cascade alive"))
    text = " ".join(c.value for c in _readout(view).controls if hasattr(c, "value"))
    assert "assumed" in text.lower()
    assert f"×{QME_HAZARD_MULT_MINT_LIVE:g}" in text
    assert f"×{QME_HAZARD_MULT_CREATOR_SELLING:g}" in text
    assert f"×{QME_HAZARD_MULT_CONCENTRATED:g}" not in text


def test_sensitivity_dropdown_offers_three_presets():
    view = build_live(FakePage(), on_back=lambda: None,
                      on_open_sizing=lambda: None)
    values = [o.key for o in _sensitivity(view).options]
    assert values == ["early", "balanced", "late"]
    assert _sensitivity(view).value == "balanced"
