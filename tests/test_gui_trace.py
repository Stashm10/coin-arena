import arena.gui.views.check as check_mod
from arena.models import Finding, ScanResult


class FakePage:
    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *a, **kw):
        fn(*a, **kw)

    def update(self):
        self.update_calls += 1


def _result_with_buyers(n=6):
    return ScanResult(
        mint="M" * 44, verdict="CAUTION",
        findings=[Finding("bundles", "PASS", "no bundling",
                          {"launch_buyers": n,
                           "buyers": [f"B{i}" for i in range(n)]})],
        unavailable=0, price_usd=None, symbol=None, duration_s=0.1)


def _results(view):
    return view.controls[1].controls[1]


def _render(monkeypatch, result, key="k"):
    monkeypatch.setattr(check_mod, "load_settings",
                        lambda: type("S", (), {"helius_key": key})())
    monkeypatch.setattr(check_mod, "run_scan",
                        lambda mint, settings, on_done, on_error: on_done(result))
    page = FakePage()
    view = check_mod.build_check(page, on_open_settings=lambda: None,
                                 on_open_history=lambda: None,
                                 on_back=lambda: None)
    view.controls[1].controls[0].controls[0].value = "M" * 44
    view.controls[1].controls[0].controls[1].on_click(None)
    return view


def _trace_button(view):
    for control in _results(view).controls:
        if getattr(control, "content", None) == "Trace funding graph":
            return control
    return None


def test_trace_button_appears_when_buyers_are_known(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    assert _trace_button(view) is not None


def test_trace_button_absent_without_a_key(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers(), key=None)
    assert _trace_button(view) is None


def test_trace_button_absent_without_buyers(monkeypatch):
    result = ScanResult(mint="M" * 44, verdict="CAUTION",
                        findings=[Finding("bundles", "INFO", "unavailable", {})],
                        unavailable=1, price_usd=None, symbol=None,
                        duration_s=0.1)
    view = _render(monkeypatch, result)
    assert _trace_button(view) is None


def test_clicking_trace_appends_the_entropy_sentence(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error:
            on_done({f"B{i}": "whale" for i in range(6)}))
    _trace_button(view).on_click(None)
    texts = [c.value for c in _results(view).controls if hasattr(c, "value")]
    assert any("6 of 6" in t for t in texts)


def test_trace_failure_shows_a_redacted_message(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error:
            on_error(RuntimeError("boom api-key=SECRET")))
    _trace_button(view).on_click(None)
    texts = [c.value for c in _results(view).controls if hasattr(c, "value")]
    assert any(t.startswith("trace failed:") for t in texts)
    assert not any("SECRET" in t for t in texts)
    assert any("api-key=***" in t for t in texts)


def test_clicking_trace_twice_fires_run_trace_exactly_once(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    calls = []
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error: calls.append(1))
    btn = _trace_button(view)
    btn.on_click(None)
    btn.on_click(None)
    assert len(calls) == 1


def test_trace_button_is_disabled_after_the_first_click(monkeypatch):
    view = _render(monkeypatch, _result_with_buyers())
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error:
            on_done({f"B{i}": "whale" for i in range(6)}))
    btn = _trace_button(view)
    assert btn.disabled is False
    btn.on_click(None)
    assert btn.disabled is True


def test_single_click_still_renders_the_entropy_sentence(monkeypatch):
    # Regression guard: the double-click fix must not break the happy path.
    view = _render(monkeypatch, _result_with_buyers())
    monkeypatch.setattr(
        check_mod, "run_trace",
        lambda mint, buyers, settings, on_done, on_error:
            on_done({f"B{i}": "whale" for i in range(6)}))
    _trace_button(view).on_click(None)
    texts = [c.value for c in _results(view).controls if hasattr(c, "value")]
    assert any("6 of 6" in t for t in texts)
