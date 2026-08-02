import arena.gui.views.check as check_mod
from arena.gui.views.check import build_check
from arena.models import Finding, ScanResult


class FakePage:
    """Stands in for a running Flet Page: run_thread executes synchronously
    so render logic can be asserted deterministically without a real event
    loop or window."""

    def __init__(self):
        self.update_calls = 0

    def run_thread(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def update(self):
        self.update_calls += 1


def _clean_result():
    return ScanResult(
        mint="M" * 44,
        verdict="NO_RED_FLAGS",
        findings=[
            Finding("authorities", "PASS", "mint/freeze revoked", {}),
            Finding("lp", "PASS", "LP locked", {}),
            Finding("holders", "INFO", "top10 holds 12%", {}),
        ],
        unavailable=0,
        price_usd=1.23,
        symbol="TEST",
        duration_s=0.42,
    )


def _avoid_result():
    return ScanResult(
        mint="N" * 44,
        verdict="AVOID",
        findings=[Finding("bundle", "DISQUALIFIER", "bundled mint detected", {})],
        unavailable=2,
        price_usd=None,
        symbol=None,
        duration_s=0.11,
    )


# Layout: view.controls[0] = header Row (Back, title, spacer, History,
# Settings button); view.controls[1] = centered body Column, whose
# controls[0] is the input Row (mint_field, check_btn, spinner) and
# controls[1] is the `results` Column.
def _input_row(view):
    return view.controls[1].controls[0]


def _results(view):
    return view.controls[1].controls[1]


def _settings_button(view):
    return view.controls[0].controls[4]


def _history_button(view):
    return view.controls[0].controls[3]


def test_invalid_mint_shows_inline_error_without_scanning():
    page = FakePage()
    called = {"run_scan": False}

    def fake_run_scan(*args, **kwargs):
        called["run_scan"] = True

    orig = check_mod.run_scan
    check_mod.run_scan = fake_run_scan
    try:
        view = build_check(page, on_open_settings=lambda: None,
                           on_open_history=lambda: None, on_back=lambda: None)
        do_check = _input_row(view).controls[1].on_click
        _input_row(view).controls[0].value = "notamint"
        do_check(None)
    finally:
        check_mod.run_scan = orig

    results = _results(view)
    assert called["run_scan"] is False
    assert len(results.controls) == 1
    assert results.controls[0].value == "not a valid Solana mint address"
    assert page.update_calls >= 1


def test_valid_mint_renders_verdict_panel_and_finding_rows():
    page = FakePage()
    result = _clean_result()
    captured = {}

    def fake_run_scan(mint, settings, on_done, on_error):
        captured["mint"] = mint
        on_done(result)

    orig = check_mod.run_scan
    check_mod.run_scan = fake_run_scan
    try:
        view = build_check(page, on_open_settings=lambda: None,
                           on_open_history=lambda: None, on_back=lambda: None)
        mint_field = _input_row(view).controls[0]
        do_check = _input_row(view).controls[1].on_click
        mint_field.value = "S" * 44
        do_check(None)
    finally:
        check_mod.run_scan = orig

    assert captured["mint"] == "S" * 44
    results = _results(view)
    # 1 verdict banner container + 3 finding rows = 4 (no footer, unavailable=0)
    assert len(results.controls) == 4
    banner = results.controls[0]
    assert banner.border.top.color == "#059669"  # NO_RED_FLAGS color
    row_texts = [r.controls[1].value for r in results.controls[1:]]
    assert row_texts == ["mint/freeze revoked", "LP locked", "top10 holds 12%"]
    check_btn = _input_row(view).controls[1]
    spinner = _input_row(view).controls[2]
    assert check_btn.disabled is False
    assert spinner.visible is False


def test_avoid_result_renders_disqualifier_and_unavailable_footer():
    page = FakePage()
    result = _avoid_result()

    def fake_run_scan(mint, settings, on_done, on_error):
        on_done(result)

    orig = check_mod.run_scan
    check_mod.run_scan = fake_run_scan
    try:
        view = build_check(page, on_open_settings=lambda: None,
                           on_open_history=lambda: None, on_back=lambda: None)
        _input_row(view).controls[0].value = "N" * 44
        _input_row(view).controls[1].on_click(None)
    finally:
        check_mod.run_scan = orig

    results = _results(view)
    # 1 verdict banner + 1 finding row + 1 unavailable footer = 3
    assert len(results.controls) == 3
    assert results.controls[1].controls[1].value == "bundled mint detected"
    footer = results.controls[2]
    assert "2 of 6 checks unavailable" in footer.value


def test_scan_error_renders_redacted_message():
    page = FakePage()

    def fake_run_scan(mint, settings, on_done, on_error):
        on_error(RuntimeError("boom api-key=SECRET123 leaked"))

    orig = check_mod.run_scan
    check_mod.run_scan = fake_run_scan
    try:
        view = build_check(page, on_open_settings=lambda: None,
                           on_open_history=lambda: None, on_back=lambda: None)
        _input_row(view).controls[0].value = "S" * 44
        _input_row(view).controls[1].on_click(None)
    finally:
        check_mod.run_scan = orig

    results = _results(view)
    assert len(results.controls) == 1
    msg = results.controls[0].value
    assert msg.startswith("scan failed:")
    assert "SECRET123" not in msg
    assert "api-key=***" in msg
    check_btn = _input_row(view).controls[1]
    spinner = _input_row(view).controls[2]
    assert check_btn.disabled is False
    assert spinner.visible is False


def test_invalid_value_error_from_scan_shown_verbatim():
    page = FakePage()

    def fake_run_scan(mint, settings, on_done, on_error):
        on_error(ValueError("not a valid Solana mint address"))

    orig = check_mod.run_scan
    check_mod.run_scan = fake_run_scan
    try:
        view = build_check(page, on_open_settings=lambda: None,
                           on_open_history=lambda: None, on_back=lambda: None)
        _input_row(view).controls[0].value = "S" * 44
        _input_row(view).controls[1].on_click(None)
    finally:
        check_mod.run_scan = orig

    results = _results(view)
    assert results.controls[0].value == "not a valid Solana mint address"


def test_settings_button_routes_via_callback():
    page = FakePage()
    opened = {"flag": False}
    view = build_check(page, on_open_settings=lambda: opened.__setitem__("flag", True),
                       on_open_history=lambda: None, on_back=lambda: None)
    _settings_button(view).on_click(None)
    assert opened["flag"] is True


def test_settings_button_has_no_gear_emoji():
    page = FakePage()
    view = build_check(page, on_open_settings=lambda: None,
                       on_open_history=lambda: None, on_back=lambda: None)
    assert _settings_button(view).content == "Settings"
    assert "⚙" not in str(_settings_button(view).content)


def test_view_route_and_check_button_style():
    page = FakePage()
    view = build_check(page, on_open_settings=lambda: None,
                       on_open_history=lambda: None, on_back=lambda: None)
    assert view.route == "/"
    check_btn = _input_row(view).controls[1]
    assert check_btn.disabled is None or check_btn.disabled is False


def test_history_button_routes_via_callback():
    page = FakePage()
    opened = {"flag": False}
    view = build_check(page, on_open_settings=lambda: None,
                       on_open_history=lambda: opened.__setitem__("flag", True), on_back=lambda: None)
    _history_button(view).on_click(None)
    assert opened["flag"] is True
