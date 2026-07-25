import json
import os
import stat

from arena.paths import data_dir
from arena.settings import Settings, load_settings, save_key


def test_data_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path / "d"))
    assert data_dir() == tmp_path / "d"
    assert data_dir().is_dir()


def test_no_key_is_public_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    s = load_settings()
    assert s.helius_key is None and s.mode == "public"


def test_env_key_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HELIUS_API_KEY", "env-key")
    save_key("file-key")
    s = load_settings()
    assert s.helius_key == "env-key" and s.mode == "full"


def test_save_key_roundtrip_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    save_key("abc-123")
    assert load_settings().helius_key == "abc-123"
    mode = stat.S_IMODE(os.stat(tmp_path / "config.json").st_mode)
    assert mode == 0o600
    assert json.loads((tmp_path / "config.json").read_text())["helius_key"] == "abc-123"


def test_save_key_tightens_existing_loose_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    p = tmp_path / "config.json"
    p.write_text("{}")
    os.chmod(p, 0o644)
    save_key("abc")
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
