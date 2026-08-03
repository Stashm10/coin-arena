"""Guards the bug class from finding 4 of the whole-branch review: wiring the
default recorder once caused five pre-existing tests to write watch-session
rows into the user's real production database at
~/Library/Application Support/CoinArena/arena.db. The fix is a repo-wide
autouse fixture (tests/conftest.py) so no future test that calls a bare
Store() or start_watch(...) without recorder_factory= can repeat that.
"""

from pathlib import Path

from arena.paths import data_dir
from arena.store import Store


def test_bare_data_dir_never_resolves_to_the_real_app_support_directory():
    real_dir = Path.home() / "Library" / "Application Support" / "CoinArena"
    assert data_dir() != real_dir
    assert not str(data_dir()).startswith(str(real_dir))


def test_bare_store_with_no_explicit_path_writes_under_the_test_tmp_dir(tmp_path):
    # No recorder_factory / explicit path here on purpose: this mirrors the
    # exact call shape (`Store()`) that leaked into the real database before
    # the repo-wide fixture existed.
    store = Store()
    store.start_watch_session("MintA", 1000, "balanced", 20.0, [])
    store.close()
    db_files = list(Path(data_dir()).glob("*.db"))
    assert db_files, "expected Store() to create its db under the isolated data dir"
    for f in db_files:
        assert str(f).startswith(str(tmp_path))
