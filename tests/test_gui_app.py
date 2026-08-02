import arena.gui.views.splash as splash_mod
from arena.gui.app import main


class FakeTimer:
    """Stands in for threading.Timer so build_splash's 1.5s auto-advance
    never schedules a real background thread in tests (avoids a dangling
    non-daemon timer delaying process exit). `.fn` is captured so a test can
    fire the auto-advance manually and deterministically."""

    last_instance = None

    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        FakeTimer.last_instance = self

    def start(self):
        pass  # caller fires self.fn manually instead of waiting on a real clock


class FakeWindow:
    def __init__(self):
        self.bgcolor = None
        self.width = None
        self.height = None


class FakePage:
    def __init__(self):
        self.title = None
        self.window = FakeWindow()
        self.views = []
        self.update_calls = 0

    def run_thread(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def update(self):
        self.update_calls += 1


def test_main_starts_at_splash_and_sets_window_props(monkeypatch):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    page = FakePage()
    main(page)
    assert page.title == "Coin Arena"
    assert page.window.width == 640
    assert page.window.height == 640
    assert len(page.views) == 1
    assert page.views[0].route == "/splash"


def test_routing_splash_to_check_to_settings_and_back(monkeypatch, tmp_path):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    page = FakePage()
    main(page)

    FakeTimer.last_instance.fn()
    assert page.views[0].route == "/modes"

    page.views[0].controls[0].controls[2].on_click(None)  # Rug Pull Checker
    assert page.views[0].route == "/"

    settings_btn = page.views[0].controls[0].controls[4]
    settings_btn.on_click(None)
    assert len(page.views) == 2
    assert page.views[-1].route == "/settings"

    back_btn = page.views[-1].controls[0].controls[0]
    back_btn.on_click(None)
    assert len(page.views) == 1
    assert page.views[0].route == "/"


def test_splash_advances_to_mode_picker(monkeypatch):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    page = FakePage()
    main(page)
    FakeTimer.last_instance.fn()
    assert page.views[0].route == "/modes"


def test_mode_picker_routes_to_rug_check_and_back(monkeypatch, tmp_path):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    page = FakePage()
    main(page)
    FakeTimer.last_instance.fn()

    picker = page.views[0]
    picker.controls[0].controls[2].on_click(None)   # Rug Pull Checker
    assert page.views[0].route == "/"

    back_btn = page.views[0].controls[0].controls[0]
    back_btn.on_click(None)
    assert page.views[0].route == "/modes"


def test_mode_picker_routes_to_qme(monkeypatch, tmp_path):
    monkeypatch.setattr(splash_mod.threading, "Timer", FakeTimer)
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    page = FakePage()
    main(page)
    FakeTimer.last_instance.fn()
    page.views[0].controls[0].controls[3].on_click(None)   # QME
    assert page.views[0].route == "/live"
