import os
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("ARENA_DATA_DIR")
    if override:
        d = Path(override)
    else:
        d = Path.home() / "Library" / "Application Support" / "CoinArena"
    d.mkdir(parents=True, exist_ok=True)
    return d
