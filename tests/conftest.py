import pytest


@pytest.fixture(autouse=True)
def _isolated_arena_data_dir(tmp_path, monkeypatch):
    """Repo-wide safety net: point ARENA_DATA_DIR at a throwaway per-test
    directory so a bare Store() or a start_watch() call that omits
    recorder_factory can never resolve to the user's real
    ~/Library/Application Support/CoinArena database.

    This must not fight a test that sets ARENA_DATA_DIR itself (see
    test_gui_history.py, test_gui_app.py, test_settings.py, etc.) — it uses
    the same function-scoped `monkeypatch` fixture instance as the test
    body, so a later monkeypatch.setenv("ARENA_DATA_DIR", ...) inside the
    test simply overrides the value set here.
    """
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
