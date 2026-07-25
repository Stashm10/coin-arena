import json
import os
from dataclasses import dataclass

from arena.paths import data_dir


@dataclass
class Settings:
    helius_key: str | None

    @property
    def mode(self) -> str:
        return "full" if self.helius_key else "public"


def _config_path():
    return data_dir() / "config.json"


def load_settings() -> Settings:
    env_key = os.environ.get("HELIUS_API_KEY")
    if env_key:
        return Settings(helius_key=env_key)
    p = _config_path()
    if p.exists():
        try:
            key = json.loads(p.read_text()).get("helius_key") or None
        except (json.JSONDecodeError, OSError):
            key = None
        return Settings(helius_key=key)
    return Settings(helius_key=None)


def save_key(key: str) -> None:
    p = _config_path()
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"helius_key": key}))
    os.chmod(p, 0o600)  # tighten a pre-existing looser file too (O_CREAT mode only applies at creation)
