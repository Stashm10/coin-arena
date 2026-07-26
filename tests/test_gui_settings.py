import arena.gui.views.settings as settings_mod
from arena.gui.views.settings import build_settings


class FakePage:
    def __init__(self):
        self.update_calls = 0
        self.launched = []

    def update(self):
        self.update_calls += 1

    def launch_url(self, url):
        self.launched.append(url)


def _do_save(view):
    return view.controls[4].controls[0].on_click


def _key_field(view):
    return view.controls[3]


def _saved_note(view):
    return view.controls[4].controls[1]


def test_empty_key_shows_inline_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    page = FakePage()
    view = build_settings(page, on_back=lambda: None)
    _key_field(view).value = "   "
    _do_save(view)(None)
    assert _saved_note(view).value == "enter a key first"


def test_save_key_oserror_shows_redacted_inline_message_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)

    def boom(key):
        raise OSError("disk full at api-key=SECRET999")

    monkeypatch.setattr(settings_mod, "save_key", boom)
    page = FakePage()
    view = build_settings(page, on_back=lambda: None)
    _key_field(view).value = "some-key"
    # Should not raise despite save_key blowing up.
    _do_save(view)(None)
    note = _saved_note(view).value
    assert note.startswith("could not save key:")
    assert "SECRET999" not in note
    assert "api-key=***" in note


def test_successful_save_clears_field_and_updates_status(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    page = FakePage()
    view = build_settings(page, on_back=lambda: None)
    _key_field(view).value = "abc123"
    _do_save(view)(None)
    assert _key_field(view).value == ""
    assert _saved_note(view).value == "key set ✓"
    assert view.controls[2].value == "Full mode (Helius key set)"
