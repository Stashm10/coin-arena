"""Live capture tests. Run manually: .venv/bin/pytest -m live -v
Needs HELIUS_API_KEY in env (or saved key + ARENA_DATA_DIR unset)."""
import json

import httpx
import pytest

from arena.engine import check_mint
from arena.settings import load_settings
from arena.store import Store

pytestmark = pytest.mark.live

WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"  # established coin


async def test_live_scan_established_coin(tmp_path):
    settings = load_settings()
    assert settings.helius_key, "needs a Helius key for the live test"
    store = Store(tmp_path / "live.db")
    async with httpx.AsyncClient() as client:
        r = await check_mint(WIF, settings, store, client)
    print(json.dumps([{ "check": f.check, "severity": f.severity,
                        "evidence": f.evidence} for f in r.findings], indent=2))
    assert len(r.findings) == 6
    assert r.verdict in ("AVOID", "CAUTION", "NO_RED_FLAGS")
    assert r.duration_s < 30
