# Coin Arena Engine + CLI Implementation Plan (Milestone 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Coin Arena analysis engine and debug CLI: `python -m arena check <mint>` runs six parallel rug checks and prints an AVOID / CAUTION / NO RED FLAGS verdict with evidence in ~5–10s, logging every scan to SQLite; `verify` labels past scans with real outcomes; `report` shows per-flag hit rates.

**Architecture:** Pure-library engine (no GUI imports anywhere): `RpcClient` (Helius full mode / public degraded mode) → shared `Birth` context (coin's earliest transactions) → six check coroutines run concurrently with per-check timeouts → categorical verdict → SQLite store. CLI is a thin wrapper. Milestone 2 (Flet GUI + packaging) is a separate plan that consumes `engine.check_mint` unchanged.

**Tech Stack:** Python 3.11+, httpx, rich, stdlib sqlite3/json/dataclasses, pytest + pytest-asyncio. No pydantic, no web3 frameworks, no flet (that's milestone 2).

**Spec:** `docs/superpowers/specs/2026-07-25-coin-arena-design.md`

## Global Constraints

- Python 3.11+. Runtime deps exactly: `httpx`, `rich`. Dev: `pytest`, `pytest-asyncio`.
- Severities verbatim: `DISQUALIFIER`, `WARNING`, `PASS`, `INFO`. Verdicts verbatim: `AVOID`, `CAUTION`, `NO_RED_FLAGS` (displayed 🔴/🟡/🟢, green always captioned "no red flags ≠ safe").
- Verdict rule: any DISQUALIFIER → AVOID; else ≥2 WARNINGs → CAUTION; else NO_RED_FLAGS.
- All tunable numbers live in `arena/thresholds.py` only — never inline in checks. Spec values: top-10 share WARNING >0.35 / DISQUALIFIER >0.55; single holder WARNING >0.15; bundle buyers-in-one-slot WARNING ≥4 / DISQUALIFIER ≥8; dev prior launches WARNING ≥3 / DISQUALIFIER ≥8; per-check timeout 8s; verify min age 24h; DEAD liquidity <$1,000; RUGGED price ≤10% of price-at-scan.
- A failed/timed-out check NEVER crashes or blocks a scan: it becomes `INFO` "check unavailable", and the verdict counts it in `unavailable`.
- Public mode (no key): authorities, holders, vitals(partial) work; bundles, dev_record, funding return INFO "needs Helius key (Settings)". `RpcClient` raises `FeatureUnavailable` for enhanced/DAS calls in public mode.
- No API key is ever committed, logged, or printed: every error string passes through `redact()` (`api-key=[^&'\" ]+` → `api-key=***`). `.env`-style secrets never in repo; key lives in the data dir config, chmod 600.
- Data dir: `$ARENA_DATA_DIR` if set (tests set it to tmp), else `~/Library/Application Support/CoinArena`.
- Default `pytest` run: zero network. Live tests marked `live`, deselected via addopts.
- No trade execution. No always-on components.
- Commit after every task with trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Work in `/Users/romanstashkiv/coin_arena` on branch `feature/engine` (create from `main` at Task 1).

## File Structure

```
coin_arena/
├── pyproject.toml              # Task 1
├── arena/
│   ├── __init__.py             # Task 1 (empty)
│   ├── models.py               # Task 1 — Finding, ScanResult, severity/verdict constants
│   ├── thresholds.py           # Task 1 — every tunable number
│   ├── scoring.py              # Task 1 — verdict(findings)
│   ├── paths.py                # Task 2 — data_dir()
│   ├── settings.py             # Task 2 — Settings, load_settings, save_key
│   ├── rpc.py                  # Task 3 — RpcClient, RpcError, FeatureUnavailable, redact
│   ├── prices.py               # Task 4 — PairInfo, fetch_pair (DexScreener)
│   ├── store.py                # Task 5 — Store (scans, coin_outcomes, wallets, scan_wallets)
│   ├── birth.py                # Task 6 — Birth, fetch_birth (earliest txs, creator)
│   ├── checks/
│   │   ├── __init__.py         # Task 9 — run_all_checks (gather + timeout guard)
│   │   ├── authorities.py      # Task 7
│   │   ├── holders.py          # Task 7
│   │   ├── bundles.py          # Task 8
│   │   ├── dev_record.py       # Task 8
│   │   ├── funding.py          # Task 9
│   │   └── vitals.py           # Task 9
│   ├── engine.py               # Task 10 — check_mint orchestrator
│   ├── verify.py               # Task 11 — verify_outcomes
│   ├── report.py               # Task 11 — flag_hit_rates
│   └── __main__.py             # Task 10 (check, set-key) + Task 11 (verify, report)
└── tests/
    ├── __init__.py             # Task 1
    ├── helpers.py              # Task 3 — MockTransport router for RPC/enhanced/DexScreener
    ├── test_scoring.py         # Task 1
    ├── test_settings.py        # Task 2
    ├── test_rpc.py             # Task 3
    ├── test_prices.py          # Task 4
    ├── test_store.py           # Task 5
    ├── test_birth.py           # Task 6
    ├── test_check_authorities.py  # Task 7
    ├── test_check_holders.py   # Task 7
    ├── test_check_bundles.py   # Task 8
    ├── test_check_dev_record.py   # Task 8
    ├── test_check_funding.py   # Task 9
    ├── test_check_vitals.py    # Task 9
    ├── test_run_all.py         # Task 9
    ├── test_engine.py          # Task 10
    ├── test_verify.py          # Task 11
    ├── test_report.py          # Task 11
    └── test_live.py            # Task 11 — marked live, captures real shapes
```

---

### Task 1: Scaffolding, models, thresholds, scoring

**Files:**
- Create: `pyproject.toml`, `arena/__init__.py`, `arena/models.py`, `arena/thresholds.py`, `arena/scoring.py`, `tests/__init__.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Produces (used by every later task):
  ```python
  # arena/models.py
  DISQUALIFIER = "DISQUALIFIER"; WARNING = "WARNING"; PASS = "PASS"; INFO = "INFO"
  AVOID = "AVOID"; CAUTION = "CAUTION"; NO_RED_FLAGS = "NO_RED_FLAGS"

  @dataclass
  class Finding:
      check: str          # "authorities"|"holders"|"bundles"|"dev_record"|"funding"|"vitals"
      severity: str       # DISQUALIFIER|WARNING|PASS|INFO
      evidence: str       # human-readable sentence
      data: dict          # raw numbers/addresses for logging & future model (default {})

  @dataclass
  class ScanResult:
      mint: str
      verdict: str                  # AVOID|CAUTION|NO_RED_FLAGS
      findings: list[Finding]
      unavailable: int              # checks that returned INFO "unavailable"
      price_usd: float | None
      symbol: str | None
      duration_s: float
  ```
  `arena/scoring.py`: `verdict(findings: list[Finding]) -> str`.
  `arena/thresholds.py`: constants listed in Global Constraints, exact names in Step 4.

- [ ] **Step 1: git branch + pyproject.toml + venv**

```bash
cd /Users/romanstashkiv/coin_arena && git checkout -b feature/engine
```

`pyproject.toml`:
```toml
[project]
name = "arena"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["httpx", "rich"]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio"]

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["arena", "arena.checks"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["live: hits real network APIs"]
addopts = "-m 'not live'"
```

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```
Create empty `arena/__init__.py` and `tests/__init__.py`.

- [ ] **Step 2: Write the failing tests**

`tests/test_scoring.py`:
```python
from arena.models import (AVOID, CAUTION, DISQUALIFIER, INFO, NO_RED_FLAGS,
                          PASS, WARNING, Finding)
from arena.scoring import verdict


def f(sev):
    return Finding(check="authorities", severity=sev, evidence="x", data={})


def test_any_disqualifier_is_avoid():
    assert verdict([f(PASS), f(WARNING), f(DISQUALIFIER)]) == AVOID


def test_two_warnings_is_caution():
    assert verdict([f(WARNING), f(WARNING), f(PASS)]) == CAUTION


def test_one_warning_is_clean():
    assert verdict([f(WARNING), f(PASS), f(INFO)]) == NO_RED_FLAGS


def test_all_pass_is_clean():
    assert verdict([f(PASS), f(PASS)]) == NO_RED_FLAGS


def test_info_never_counts_toward_verdict():
    assert verdict([f(INFO)] * 6) == NO_RED_FLAGS
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: arena.models`.

- [ ] **Step 4: Implement**

`arena/models.py`:
```python
from dataclasses import dataclass, field

DISQUALIFIER = "DISQUALIFIER"
WARNING = "WARNING"
PASS = "PASS"
INFO = "INFO"

AVOID = "AVOID"
CAUTION = "CAUTION"
NO_RED_FLAGS = "NO_RED_FLAGS"

CHECK_NAMES = ["authorities", "holders", "bundles", "dev_record", "funding", "vitals"]


@dataclass
class Finding:
    check: str
    severity: str
    evidence: str
    data: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    mint: str
    verdict: str
    findings: list[Finding]
    unavailable: int
    price_usd: float | None
    symbol: str | None
    duration_s: float
```

`arena/thresholds.py`:
```python
"""Every tunable number in Coin Arena. The future fitted model replaces
scoring.py's use of these; nothing else changes."""

TOP10_SHARE_WARNING = 0.35
TOP10_SHARE_DISQUALIFIER = 0.55
SINGLE_HOLDER_WARNING = 0.15

BUNDLE_BUYERS_WARNING = 4
BUNDLE_BUYERS_DISQUALIFIER = 8
LAUNCH_WINDOW_S = 60

DEV_LAUNCHES_WARNING = 3
DEV_LAUNCHES_DISQUALIFIER = 8
DEV_HISTORY_SAMPLE = 100

CHECK_TIMEOUT_S = 8.0

VERIFY_MIN_AGE_S = 24 * 3600
DEAD_LIQUIDITY_USD = 1000.0
RUG_PRICE_RATIO = 0.10

FUNDING_MAX_SIGS = 1000  # creator wallets busier than this: funding check bails
```

`arena/scoring.py`:
```python
from arena.models import AVOID, CAUTION, DISQUALIFIER, NO_RED_FLAGS, WARNING, Finding


def verdict(findings: list[Finding]) -> str:
    severities = [f.severity for f in findings]
    if DISQUALIFIER in severities:
        return AVOID
    if severities.count(WARNING) >= 2:
        return CAUTION
    return NO_RED_FLAGS
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_scoring.py -v` — Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml arena/ tests/
git commit -m "feat: scaffolding, models, thresholds, verdict scoring"
```

---

### Task 2: Paths + settings (key storage)

**Files:**
- Create: `arena/paths.py`, `arena/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces:
  - `arena/paths.py`: `data_dir() -> Path` — `$ARENA_DATA_DIR` if set, else `~/Library/Application Support/CoinArena`; created (parents, exist_ok) on every call.
  - `arena/settings.py`:
    ```python
    @dataclass
    class Settings:
        helius_key: str | None
        @property
        def mode(self) -> str: ...   # "full" if key else "public"
    def load_settings() -> Settings  # env HELIUS_API_KEY wins, else config.json in data_dir
    def save_key(key: str) -> None   # writes {"helius_key": ...} to config.json, chmod 0o600
    ```

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_settings.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`arena/paths.py`:
```python
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
```

`arena/settings.py`:
```python
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
    p.write_text(json.dumps({"helius_key": key}))
    os.chmod(p, 0o600)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_settings.py -v` — Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add arena/paths.py arena/settings.py tests/test_settings.py
git commit -m "feat: data dir and key settings with 600 perms"
```

---

### Task 3: RpcClient (full/public modes) + test router

**Files:**
- Create: `arena/rpc.py`, `tests/helpers.py`
- Test: `tests/test_rpc.py`

**Interfaces:**
- Produces:
  ```python
  # arena/rpc.py
  class RpcError(Exception): ...          # RPC-level error or bad HTTP
  class FeatureUnavailable(Exception): ...  # enhanced/DAS called in public mode

  def redact(text: str) -> str            # api-key=... -> api-key=***

  class RpcClient:
      mode: str                            # "full"|"public"
      def __init__(self, client: httpx.AsyncClient, helius_key: str | None): ...
      async def rpc(self, method: str, params: list) -> dict|list   # JSON-RPC result
      async def das(self, method: str, params: dict) -> dict        # DAS (full only)
      async def enhanced_txs(self, address: str, before: str | None = None,
                             limit: int = 100) -> list[dict]        # full only
      async def enhanced_batch(self, signatures: list[str]) -> list[dict]  # full only
  ```
  URLs: full RPC/DAS `https://mainnet.helius-rpc.com/?api-key={key}`; public RPC `https://api.mainnet-beta.solana.com`; enhanced GET `https://api.helius.xyz/v0/addresses/{address}/transactions`; enhanced batch POST `https://api.helius.xyz/v0/transactions` body `{"transactions": [...]}` (api-key as query param).
- Produces `tests/helpers.py`: `make_client(rpc_methods: dict, enhanced: dict | None = None, dexscreener: dict | None = None) -> httpx.AsyncClient` — a MockTransport router used by ALL later network tests:
  - JSON-RPC POSTs are answered from `rpc_methods[method]` (value = `result` payload, or an int = HTTP status, or a callable `(params) -> result`).
  - GET `…/v0/addresses/{addr}/transactions` answered from `enhanced[addr]` (list, sliced by `limit`, filtered by `before`: entries strictly after the given signature in list order are excluded — list is newest-first like Helius).
  - POST `…/v0/transactions` answered by looking up each requested signature in `enhanced["__by_sig__"]`.
  - GET `api.dexscreener.com/latest/dex/tokens/{mint}` answered from `dexscreener` dict (mint -> response json).
  - Unknown route → HTTP 500 (so tests fail loudly on unexpected calls).

- [ ] **Step 1: Write tests/helpers.py**

```python
import json

import httpx


def make_client(rpc_methods=None, enhanced=None, dexscreener=None):
    rpc_methods = rpc_methods or {}
    enhanced = enhanced or {}
    dexscreener = dexscreener or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/v0/addresses/" in url:
            addr = request.url.path.split("/")[3]
            txs = enhanced.get(addr, [])
            if isinstance(txs, int):
                return httpx.Response(txs)
            before = request.url.params.get("before")
            if before:
                sigs = [t["signature"] for t in txs]
                txs = txs[sigs.index(before) + 1:] if before in sigs else txs
            limit = int(request.url.params.get("limit", 100))
            return httpx.Response(200, json=txs[:limit])
        if url.startswith("https://api.helius.xyz/v0/transactions"):
            wanted = json.loads(request.content)["transactions"]
            by_sig = enhanced.get("__by_sig__", {})
            return httpx.Response(200, json=[by_sig[s] for s in wanted if s in by_sig])
        if "api.dexscreener.com" in url:
            mint = request.url.path.split("/")[-1]
            body = dexscreener.get(mint)
            return httpx.Response(200, json=body if body is not None else {"pairs": None})
        if request.method == "POST":  # JSON-RPC
            body = json.loads(request.content)
            method = body["method"]
            spec = rpc_methods.get(method)
            if spec is None:
                return httpx.Response(500)
            if isinstance(spec, int):
                return httpx.Response(spec)
            result = spec(body["params"]) if callable(spec) else spec
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
        return httpx.Response(500)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
```

- [ ] **Step 2: Write the failing tests**

`tests/test_rpc.py`:
```python
import pytest

from arena.rpc import FeatureUnavailable, RpcClient, RpcError, redact
from tests.helpers import make_client


def test_redact():
    assert redact("url 'https://x/?api-key=abc-123' failed") == \
        "url 'https://x/?api-key=***' failed"
    assert redact("clean") == "clean"


async def test_rpc_result_roundtrip():
    async with make_client({"getSlot": 123}) as c:
        assert await RpcClient(c, "k").rpc("getSlot", []) == 123


async def test_rpc_error_raises_rpcerror_redacted():
    async with make_client({"getSlot": 500}) as c:
        with pytest.raises(RpcError) as ei:
            await RpcClient(c, "secret-key").rpc("getSlot", [])
        assert "secret-key" not in str(ei.value)


async def test_public_mode_blocks_enhanced_and_das():
    async with make_client() as c:
        rpc = RpcClient(c, None)
        assert rpc.mode == "public"
        with pytest.raises(FeatureUnavailable):
            await rpc.enhanced_txs("SomeAddr")
        with pytest.raises(FeatureUnavailable):
            await rpc.das("getTokenAccounts", {})


async def test_enhanced_txs_full_mode():
    txs = [{"signature": "s2"}, {"signature": "s1"}]
    async with make_client(enhanced={"Addr1": txs}) as c:
        got = await RpcClient(c, "k").enhanced_txs("Addr1", limit=1)
        assert got == [{"signature": "s2"}]


async def test_enhanced_batch():
    async with make_client(enhanced={"__by_sig__": {"s1": {"signature": "s1"}}}) as c:
        got = await RpcClient(c, "k").enhanced_batch(["s1"])
        assert got == [{"signature": "s1"}]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_rpc.py -v` — Expected: FAIL, `ModuleNotFoundError: arena.rpc`.

- [ ] **Step 4: Implement arena/rpc.py**

```python
import re

import httpx

HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key={key}"
PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
ENHANCED_TX = "https://api.helius.xyz/v0/addresses/{address}/transactions"
ENHANCED_BATCH = "https://api.helius.xyz/v0/transactions"


class RpcError(Exception):
    pass


class FeatureUnavailable(Exception):
    """Raised when an enhanced/DAS call is attempted without a Helius key."""


def redact(text: str) -> str:
    return re.sub(r"api-key=[^&'\" ]+", "api-key=***", text)


class RpcClient:
    def __init__(self, client: httpx.AsyncClient, helius_key: str | None):
        self._client = client
        self._key = helius_key
        self.mode = "full" if helius_key else "public"
        self._rpc_url = HELIUS_RPC.format(key=helius_key) if helius_key else PUBLIC_RPC

    async def rpc(self, method: str, params: list):
        try:
            resp = await self._client.post(
                self._rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise RpcError(f"{method}: {redact(str(exc))}") from None
        if "error" in body:
            raise RpcError(f"{method}: {redact(str(body['error']))}")
        return body["result"]

    def _require_key(self):
        if not self._key:
            raise FeatureUnavailable("needs Helius key (Settings)")

    async def das(self, method: str, params: dict):
        """DAS methods ride the same Helius JSON-RPC URL; the separate method
        exists only to enforce that a key is present (public RPC has no DAS)."""
        self._require_key()
        return await self.rpc(method, params)

    async def enhanced_txs(self, address: str, before: str | None = None,
                           limit: int = 100) -> list[dict]:
        self._require_key()
        params: dict = {"api-key": self._key, "limit": limit}
        if before:
            params["before"] = before
        try:
            resp = await self._client.get(ENHANCED_TX.format(address=address),
                                          params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise RpcError(f"enhanced_txs: {redact(str(exc))}") from None

    async def enhanced_batch(self, signatures: list[str]) -> list[dict]:
        self._require_key()
        try:
            resp = await self._client.post(
                ENHANCED_BATCH, params={"api-key": self._key},
                json={"transactions": signatures}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise RpcError(f"enhanced_batch: {redact(str(exc))}") from None
```

Note: `das()` and `rpc()` share their body deliberately via near-identical code — Helius serves DAS methods on the same JSON-RPC URL; the separate method exists only to enforce `_require_key`. Do not merge them: public `rpc()` must work keyless.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_rpc.py -v` — Expected: 6 PASSED. Then full suite: `.venv/bin/pytest` — all green.

- [ ] **Step 6: Commit**

```bash
git add arena/rpc.py tests/helpers.py tests/test_rpc.py
git commit -m "feat: RpcClient with full/public modes and mock router"
```

---

### Task 4: Prices (DexScreener)

**Files:**
- Create: `arena/prices.py`
- Test: `tests/test_prices.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass
  class PairInfo:
      price_usd: float | None
      liquidity_usd: float | None
      symbol: str | None
  async def fetch_pair(client: httpx.AsyncClient, mint: str) -> PairInfo | None
  ```
  Picks the pair with highest `liquidity.usd`. Returns `None` if no pairs. NEVER raises — any failure → `None` (proven pattern from the whale tracker project).

- [ ] **Step 1: Write the failing tests**

`tests/test_prices.py`:
```python
from arena.prices import fetch_pair
from tests.helpers import make_client

DS = {"MintA": {"pairs": [
    {"priceUsd": "0.5", "liquidity": {"usd": 100}, "baseToken": {"symbol": "LOW"}},
    {"priceUsd": "0.9", "liquidity": {"usd": 9000}, "baseToken": {"symbol": "FISTY"}},
]}}


async def test_picks_highest_liquidity_pair():
    async with make_client(dexscreener=DS) as c:
        p = await fetch_pair(c, "MintA")
    assert p.price_usd == 0.9 and p.liquidity_usd == 9000 and p.symbol == "FISTY"


async def test_no_pairs_returns_none():
    async with make_client(dexscreener={"MintB": {"pairs": None}}) as c:
        assert await fetch_pair(c, "MintB") is None


async def test_malformed_returns_none():
    async with make_client(dexscreener={"MintC": {"pairs": [None]}}) as c:
        assert await fetch_pair(c, "MintC") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_prices.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement arena/prices.py**

```python
from dataclasses import dataclass

import httpx

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


@dataclass
class PairInfo:
    price_usd: float | None
    liquidity_usd: float | None
    symbol: str | None


async def fetch_pair(client: httpx.AsyncClient, mint: str) -> PairInfo | None:
    """Best-liquidity pair from DexScreener. None on any failure — a missing
    price must never block or crash a scan."""
    try:
        resp = await client.get(DEXSCREENER_URL.format(mint=mint), timeout=10)
        resp.raise_for_status()
        pairs = resp.json().get("pairs") or []
        if not pairs:
            return None
        best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        liq = (best.get("liquidity") or {}).get("usd")
        return PairInfo(
            price_usd=float(best["priceUsd"]) if best.get("priceUsd") else None,
            liquidity_usd=float(liq) if liq is not None else None,
            symbol=(best.get("baseToken") or {}).get("symbol"),
        )
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_prices.py -v` — Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add arena/prices.py tests/test_prices.py
git commit -m "feat: DexScreener pair lookup"
```

---

### Task 5: Store (SQLite)

**Files:**
- Create: `arena/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `ScanResult`, `Finding` (Task 1).
- Produces:
  ```python
  class Store:
      def __init__(self, path: str | Path | None = None)   # None -> data_dir()/"arena.db"
      def save_scan(self, result: ScanResult, creator: str | None,
                    funder: str | None, top_holders: list[str]) -> None
      def unverified_scans(self, older_than_ts: int) -> list[dict]
          # dicts: {mint, ts, price_usd_at_scan}; scans with no outcome row yet
      def record_outcome(self, mint: str, outcome: str) -> None
          # writes coin_outcomes + bumps wallets counters via scan_wallets
      def funder_rugged_count(self, funder: str) -> int
          # coins where this address was role='funder' and outcome='RUGGED'
      def survivor_wallet_count(self, addresses: list[str]) -> int
          # how many of addresses have times_in_survivors >= 1
      def scans_with_outcomes(self) -> list[dict]   # {scan_json, outcome} for report
      def recent_scans(self, limit: int = 50) -> list[dict]
      def close(self) -> None
  ```
- Schema (executescript, CREATE TABLE IF NOT EXISTS):
  - `scans(id INTEGER PK AUTOINCREMENT, ts INTEGER, mint TEXT, symbol TEXT, verdict TEXT, price_usd_at_scan REAL, scan_json TEXT)`
  - `coin_outcomes(mint TEXT PRIMARY KEY, scanned_ts INTEGER, verified_ts INTEGER, outcome TEXT)`  -- RUGGED|DEAD|ALIVE
  - `wallets(address TEXT PRIMARY KEY, times_seen INTEGER DEFAULT 0, times_in_rugged INTEGER DEFAULT 0, times_in_survivors INTEGER DEFAULT 0)`
  - `scan_wallets(mint TEXT, address TEXT, role TEXT, UNIQUE(mint, address, role))`  -- role: creator|funder|top_holder
- Outcome counter rule: `record_outcome` bumps `times_in_rugged` when outcome ∈ (RUGGED, DEAD)? **No** — spec separates them: RUGGED bumps `times_in_rugged`; ALIVE bumps `times_in_survivors`; DEAD bumps neither (a quietly dying coin isn't evidence of malice or skill).
- `scan_json` = `json.dumps([{"check":..., "severity":..., "evidence":..., "data":...}, ...])`.

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:
```python
import json

from arena.models import Finding, ScanResult
from arena.store import Store


def scan(mint="M1", verdict="AVOID", price=0.5):
    return ScanResult(mint=mint, verdict=verdict,
                      findings=[Finding("authorities", "DISQUALIFIER", "e", {"x": 1})],
                      unavailable=0, price_usd=price, symbol="T", duration_s=1.0)


def make(tmp_path):
    return Store(tmp_path / "a.db")


def test_save_and_unverified(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan(), creator="Dev1", funder="Fund1", top_holders=["H1", "H2"])
    rows = s.unverified_scans(older_than_ts=2**62)
    assert len(rows) == 1
    assert rows[0]["mint"] == "M1" and rows[0]["price_usd_at_scan"] == 0.5
    s.close()


def test_record_outcome_bumps_wallets(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), "Dev1", "Fund1", ["H1"])
    s.save_scan(scan("M2"), "Dev1", "Fund1", ["H1"])
    s.record_outcome("M1", "RUGGED")
    s.record_outcome("M2", "ALIVE")
    assert s.funder_rugged_count("Fund1") == 1
    assert s.survivor_wallet_count(["H1", "Nobody"]) == 1
    assert s.unverified_scans(2**62) == []
    s.close()


def test_dead_bumps_neither(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), "Dev1", "Fund1", ["H1"])
    s.record_outcome("M1", "DEAD")
    assert s.funder_rugged_count("Fund1") == 0
    assert s.survivor_wallet_count(["H1"]) == 0
    s.close()


def test_scan_json_roundtrip_and_report_rows(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), None, None, [])
    s.record_outcome("M1", "RUGGED")
    rows = s.scans_with_outcomes()
    assert rows[0]["outcome"] == "RUGGED"
    parsed = json.loads(rows[0]["scan_json"])
    assert parsed[0]["check"] == "authorities" and parsed[0]["data"] == {"x": 1}
    s.close()


def test_duplicate_scan_wallets_ignored(tmp_path):
    s = make(tmp_path)
    s.save_scan(scan("M1"), "Dev1", "Dev1", ["Dev1"])   # same addr, 3 roles: ok
    s.save_scan(scan("M1"), "Dev1", None, ["Dev1"])     # rescan: no unique violation
    s.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_store.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement arena/store.py**

```python
import json
import time
from dataclasses import asdict
from pathlib import Path

import sqlite3

from arena.paths import data_dir
from arena.models import ScanResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    mint TEXT NOT NULL,
    symbol TEXT,
    verdict TEXT NOT NULL,
    price_usd_at_scan REAL,
    scan_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coin_outcomes (
    mint TEXT PRIMARY KEY,
    scanned_ts INTEGER,
    verified_ts INTEGER,
    outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wallets (
    address TEXT PRIMARY KEY,
    times_seen INTEGER DEFAULT 0,
    times_in_rugged INTEGER DEFAULT 0,
    times_in_survivors INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS scan_wallets (
    mint TEXT NOT NULL,
    address TEXT NOT NULL,
    role TEXT NOT NULL,
    UNIQUE(mint, address, role)
);
"""


class Store:
    def __init__(self, path: str | Path | None = None):
        self.conn = sqlite3.connect(path or data_dir() / "arena.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def save_scan(self, result: ScanResult, creator: str | None,
                  funder: str | None, top_holders: list[str]) -> None:
        self.conn.execute(
            "INSERT INTO scans (ts, mint, symbol, verdict, price_usd_at_scan, scan_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (int(time.time()), result.mint, result.symbol, result.verdict,
             result.price_usd, json.dumps([asdict(f) for f in result.findings])))
        links = [(result.mint, creator, "creator"), (result.mint, funder, "funder")]
        links += [(result.mint, h, "top_holder") for h in top_holders]
        for mint, addr, role in links:
            if not addr:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO scan_wallets (mint, address, role) VALUES (?,?,?)",
                (mint, addr, role))
            self.conn.execute(
                "INSERT INTO wallets (address, times_seen) VALUES (?, 1) "
                "ON CONFLICT(address) DO UPDATE SET times_seen = times_seen + 1",
                (addr,))
        self.conn.commit()

    def unverified_scans(self, older_than_ts: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.mint, MIN(s.ts) AS ts, s.price_usd_at_scan FROM scans s "
            "LEFT JOIN coin_outcomes o ON o.mint = s.mint "
            "WHERE o.mint IS NULL GROUP BY s.mint HAVING MIN(s.ts) <= ?",
            (older_than_ts,)).fetchall()
        return [dict(r) for r in rows]

    def record_outcome(self, mint: str, outcome: str) -> None:
        row = self.conn.execute("SELECT MIN(ts) AS t FROM scans WHERE mint = ?",
                                (mint,)).fetchone()
        self.conn.execute(
            "INSERT INTO coin_outcomes (mint, scanned_ts, verified_ts, outcome) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(mint) DO UPDATE SET "
            "outcome = excluded.outcome, verified_ts = excluded.verified_ts",
            (mint, row["t"], int(time.time()), outcome))
        col = {"RUGGED": "times_in_rugged", "ALIVE": "times_in_survivors"}.get(outcome)
        if col:
            self.conn.execute(
                f"UPDATE wallets SET {col} = {col} + 1 WHERE address IN "
                "(SELECT address FROM scan_wallets WHERE mint = ?)", (mint,))
        self.conn.commit()

    def funder_rugged_count(self, funder: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT sw.mint) AS n FROM scan_wallets sw "
            "JOIN coin_outcomes o ON o.mint = sw.mint "
            "WHERE sw.address = ? AND sw.role = 'funder' AND o.outcome = 'RUGGED'",
            (funder,)).fetchone()
        return row["n"]

    def survivor_wallet_count(self, addresses: list[str]) -> int:
        if not addresses:
            return 0
        q = ",".join("?" * len(addresses))
        row = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM wallets WHERE address IN ({q}) "
            "AND times_in_survivors >= 1", addresses).fetchone()
        return row["n"]

    def scans_with_outcomes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.scan_json, o.outcome FROM scans s "
            "JOIN coin_outcomes o ON o.mint = s.mint").fetchall()
        return [dict(r) for r in rows]

    def recent_scans(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.ts, s.mint, s.symbol, s.verdict, o.outcome FROM scans s "
            "LEFT JOIN coin_outcomes o ON o.mint = s.mint "
            "ORDER BY s.id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_store.py -v` — Expected: 5 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/store.py tests/test_store.py
git commit -m "feat: SQLite store with wallet reputation counters"
```

---

### Task 6: Birth context (earliest transactions, creator)

**Files:**
- Create: `arena/birth.py`
- Test: `tests/test_birth.py`

**Interfaces:**
- Consumes: `RpcClient` (Task 3).
- Produces:
  ```python
  @dataclass
  class Birth:
      creation_sig: str | None
      creator: str | None       # fee payer of the creation tx
      created_ts: int | None    # blockTime of oldest signature
      first_sig_infos: list[dict]  # oldest-first [{signature, slot, blockTime}], ≤200
      first_txs: list[dict]     # parsed earliest txs, oldest-first, ≤40 ([] in public mode)
  async def fetch_birth(rpc: RpcClient, mint: str) -> Birth
  ```
- Method: `getSignaturesForAddress(mint, {limit:1000})` repeatedly with `before=<oldest sig so far>` until a page returns <1000 entries (cap: 5 pages; if cap hit, treat the oldest page seen as authoritative — the coin is unusually old/busy, checks degrade gracefully). The LAST entry of the final page is the creation signature (Solana returns newest-first). `created_ts` = its blockTime. Keep the oldest ≤200 sig infos, reversed to oldest-first. In full mode, `enhanced_batch` on the oldest ≤40 signatures → `first_txs` (oldest-first); creator = `feePayer` of the creation tx. In public mode `first_txs=[]` and creator = `getTransaction(creation_sig, {encoding:"jsonParsed", maxSupportedTransactionVersion:0})` → `result.transaction.message.accountKeys[0].pubkey` (fee payer is always the first account key); creator None if that call fails.
- Any failure anywhere → return a Birth with whatever was gathered (fields None/[]). Never raises.

- [ ] **Step 1: Write the failing tests**

`tests/test_birth.py`:
```python
from arena.birth import fetch_birth
from arena.rpc import RpcClient
from tests.helpers import make_client

SIGS = [  # newest-first, as Solana returns
    {"signature": "s3", "slot": 30, "blockTime": 300},
    {"signature": "s2", "slot": 20, "blockTime": 200},
    {"signature": "s1", "slot": 10, "blockTime": 100},
]
BY_SIG = {"__by_sig__": {
    "s1": {"signature": "s1", "feePayer": "Dev1", "slot": 10},
    "s2": {"signature": "s2", "feePayer": "Buyer", "slot": 20},
    "s3": {"signature": "s3", "feePayer": "Buyer2", "slot": 30},
}}


async def test_full_mode_birth():
    async with make_client({"getSignaturesForAddress": SIGS}, enhanced=BY_SIG) as c:
        b = await fetch_birth(RpcClient(c, "k"), "Mint1")
    assert b.creation_sig == "s1" and b.creator == "Dev1" and b.created_ts == 100
    assert [s["signature"] for s in b.first_sig_infos] == ["s1", "s2", "s3"]
    assert [t["signature"] for t in b.first_txs] == ["s1", "s2", "s3"]


async def test_public_mode_uses_get_transaction():
    rpc_methods = {
        "getSignaturesForAddress": SIGS,
        "getTransaction": {"transaction": {"message": {"accountKeys": [
            {"pubkey": "Dev1"}, {"pubkey": "Other"}]}}},
    }
    async with make_client(rpc_methods) as c:
        b = await fetch_birth(RpcClient(c, None), "Mint1")
    assert b.creator == "Dev1" and b.first_txs == []


async def test_rpc_failure_returns_empty_birth():
    async with make_client({"getSignaturesForAddress": 500}) as c:
        b = await fetch_birth(RpcClient(c, "k"), "Mint1")
    assert b.creation_sig is None and b.creator is None and b.first_txs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_birth.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement arena/birth.py**

```python
import logging
from dataclasses import dataclass, field

from arena.rpc import FeatureUnavailable, RpcClient, RpcError

log = logging.getLogger(__name__)

MAX_SIG_PAGES = 5
KEEP_SIGS = 200
KEEP_TXS = 40


@dataclass
class Birth:
    creation_sig: str | None = None
    creator: str | None = None
    created_ts: int | None = None
    first_sig_infos: list[dict] = field(default_factory=list)
    first_txs: list[dict] = field(default_factory=list)


async def fetch_birth(rpc: RpcClient, mint: str) -> Birth:
    """Locate the coin's creation and earliest activity. Best-effort:
    partial data on failure, never raises."""
    birth = Birth()
    try:
        page = await rpc.rpc("getSignaturesForAddress", [mint, {"limit": 1000}])
        pages = 1
        while len(page) == 1000 and pages < MAX_SIG_PAGES:
            older = await rpc.rpc("getSignaturesForAddress",
                                  [mint, {"limit": 1000, "before": page[-1]["signature"]}])
            if not older:
                break
            page = older
            pages += 1
    except RpcError as exc:
        log.warning("birth: signature fetch failed for %s: %s", mint, exc)
        return birth

    if not page:
        return birth
    oldest_first = list(reversed(page))[:KEEP_SIGS]
    birth.first_sig_infos = oldest_first
    birth.creation_sig = oldest_first[0]["signature"]
    birth.created_ts = oldest_first[0].get("blockTime")

    try:
        sigs = [s["signature"] for s in oldest_first[:KEEP_TXS]]
        txs = await rpc.enhanced_batch(sigs)
        by_sig = {t.get("signature"): t for t in txs if isinstance(t, dict)}
        birth.first_txs = [by_sig[s] for s in sigs if s in by_sig]
        creation = by_sig.get(birth.creation_sig)
        if creation:
            birth.creator = creation.get("feePayer")
    except FeatureUnavailable:
        try:  # public mode: fee payer via standard getTransaction
            tx = await rpc.rpc("getTransaction", [
                birth.creation_sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            keys = tx["transaction"]["message"]["accountKeys"]
            birth.creator = keys[0]["pubkey"]
        except (RpcError, KeyError, IndexError, TypeError):
            pass
    except RpcError as exc:
        log.warning("birth: enhanced batch failed for %s: %s", mint, exc)
    return birth
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_birth.py -v` — Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add arena/birth.py tests/test_birth.py
git commit -m "feat: birth context - creation tx, creator, earliest activity"
```

---

### Task 7: Checks — authorities + holders

**Files:**
- Create: `arena/checks/__init__.py` (empty for now — orchestrator comes in Task 9), `arena/checks/authorities.py`, `arena/checks/holders.py`
- Test: `tests/test_check_authorities.py`, `tests/test_check_holders.py`

**Interfaces:**
- Every check module in Tasks 7–9 exposes the SAME signature (uniformity is what lets the orchestrator stay dumb):
  ```python
  async def run(rpc: RpcClient, store: Store, mint: str, birth: Birth,
                pair: PairInfo | None) -> Finding
  ```
  Checks may raise `RpcError`/`FeatureUnavailable`/anything — the Task 9 orchestrator converts exceptions/timeouts to INFO "check unavailable". Individual checks do NOT catch their own transport errors.
- `authorities.run`: `rpc.rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])` → `value.data.parsed.info`. `mintAuthority` present/non-null → DISQUALIFIER "Mint authority not revoked — dev can print supply". Else `freezeAuthority` present → DISQUALIFIER "Freeze authority not revoked — dev can block selling". Else PASS "Mint & freeze authority revoked". `data` = `{"mint_authority": bool, "freeze_authority": bool}`.
- `holders.run`: `getTokenLargestAccounts(mint)` → top 20 token accounts (uiAmount), `getTokenSupply(mint)` → total uiAmount; resolve owners via `getMultipleAccounts([...], jsonParsed)`; drop program-owned owners (owner account's `owner != SYSTEM_PROGRAM` via a second `getMultipleAccounts` with base64, same technique as the whale tracker's watchlist); compute top-10 human share and max single human share. Severity per thresholds. `data` = `{"top10_share": float, "max_single": float, "owners": [top human owners, ≤20]}`. Evidence like "Top 10 humans hold 61% of supply".

- [ ] **Step 1: Write the failing tests**

`tests/test_check_authorities.py`:
```python
from arena.birth import Birth
from arena.checks import authorities
from arena.models import DISQUALIFIER, PASS
from arena.rpc import RpcClient
from tests.helpers import make_client


def acct(mint_auth, freeze_auth):
    return {"value": {"data": {"parsed": {"info": {
        "mintAuthority": mint_auth, "freezeAuthority": freeze_auth,
        "decimals": 6, "supply": "1000"}}}}}


async def test_live_mint_authority_disqualifies():
    async with make_client({"getAccountInfo": acct("DevKey", None)}) as c:
        f = await authorities.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == DISQUALIFIER and "print" in f.evidence


async def test_freeze_authority_disqualifies():
    async with make_client({"getAccountInfo": acct(None, "DevKey")}) as c:
        f = await authorities.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == DISQUALIFIER and "block selling" in f.evidence


async def test_both_revoked_passes():
    async with make_client({"getAccountInfo": acct(None, None)}) as c:
        f = await authorities.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == PASS
    assert f.data == {"mint_authority": False, "freeze_authority": False}
```

`tests/test_check_holders.py`:
```python
from arena.birth import Birth
from arena.checks import holders
from arena.models import DISQUALIFIER, PASS, WARNING
from arena.rpc import RpcClient
from tests.helpers import make_client

SYSTEM = "11111111111111111111111111111111"


def rpc_methods(amounts_by_owner, supply=1000.0):
    """amounts_by_owner: [(owner, ui_amount, owner_program)] for top accounts."""
    largest = {"value": [
        {"address": f"TA{i}", "uiAmount": amt}
        for i, (_, amt, _) in enumerate(amounts_by_owner)]}
    def multi(params):
        accounts = params[0]
        if accounts and accounts[0].startswith("TA"):  # token accounts -> owners
            return {"value": [
                {"data": {"parsed": {"info": {"owner": amounts_by_owner[int(a[2:])][0]}}}}
                for a in accounts]}
        owner_prog = {o: prog for (o, _, prog) in amounts_by_owner}
        return {"value": [{"owner": owner_prog[a]} for a in accounts]}
    return {
        "getTokenLargestAccounts": largest,
        "getTokenSupply": {"value": {"uiAmount": supply}},
        "getMultipleAccounts": multi,
    }


async def test_concentrated_supply_disqualifies():
    m = rpc_methods([("W1", 300, SYSTEM), ("W2", 300, SYSTEM)], supply=1000)
    async with make_client(m) as c:  # top-10 human share = 0.6 > 0.55
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == DISQUALIFIER
    assert f.data["top10_share"] == 0.6
    assert f.data["owners"] == ["W1", "W2"]


async def test_pool_excluded_and_single_holder_warning():
    m = rpc_methods([("Pool", 800, "RaydiumProgram111"), ("W1", 200, SYSTEM)],
                    supply=1000)
    async with make_client(m) as c:  # human share 0.2, but W1 alone 0.2 > 0.15
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == WARNING and f.data["max_single"] == 0.2


async def test_dispersed_supply_passes():
    m = rpc_methods([(f"W{i}", 20, SYSTEM) for i in range(10)], supply=1000)
    async with make_client(m) as c:  # 0.2 total, max single 0.02
        f = await holders.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == PASS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_check_authorities.py tests/test_check_holders.py -v`
Expected: FAIL, `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Implement**

Create empty `arena/checks/__init__.py`.

`arena/checks/authorities.py`:
```python
from arena.birth import Birth
from arena.models import DISQUALIFIER, PASS, Finding
from arena.prices import PairInfo
from arena.rpc import RpcClient


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    result = await rpc.rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    info = result["value"]["data"]["parsed"]["info"]
    mint_auth = info.get("mintAuthority") is not None
    freeze_auth = info.get("freezeAuthority") is not None
    data = {"mint_authority": mint_auth, "freeze_authority": freeze_auth}
    if mint_auth:
        return Finding("authorities", DISQUALIFIER,
                       "Mint authority not revoked — dev can print supply", data)
    if freeze_auth:
        return Finding("authorities", DISQUALIFIER,
                       "Freeze authority not revoked — dev can block selling", data)
    return Finding("authorities", PASS, "Mint & freeze authority revoked", data)
```

`arena/checks/holders.py`:
```python
from arena.birth import Birth
from arena.models import DISQUALIFIER, PASS, WARNING, Finding
from arena.prices import PairInfo
from arena.rpc import RpcClient
from arena.thresholds import (SINGLE_HOLDER_WARNING, TOP10_SHARE_DISQUALIFIER,
                              TOP10_SHARE_WARNING)

SYSTEM_PROGRAM = "11111111111111111111111111111111"


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    largest = await rpc.rpc("getTokenLargestAccounts", [mint])
    supply = await rpc.rpc("getTokenSupply", [mint])
    total = (supply["value"] or {}).get("uiAmount") or 0
    entries = [(v["address"], v.get("uiAmount") or 0) for v in largest["value"]]
    if not entries or not total:
        return Finding("holders", PASS, "No holder data yet", {"owners": []})

    token_accounts = [a for a, _ in entries]
    parsed = await rpc.rpc("getMultipleAccounts",
                           [token_accounts, {"encoding": "jsonParsed"}])
    owners_by_ta = {}
    for (ta, _), acc in zip(entries, parsed["value"]):
        if acc:
            owners_by_ta[ta] = acc["data"]["parsed"]["info"]["owner"]

    unique_owners = list(dict.fromkeys(owners_by_ta.values()))
    owner_accs = await rpc.rpc("getMultipleAccounts",
                               [unique_owners, {"encoding": "base64"}])
    human = {o for o, acc in zip(unique_owners, owner_accs["value"])
             if acc is not None and acc.get("owner") == SYSTEM_PROGRAM}

    amounts: dict[str, float] = {}
    for ta, amt in entries:
        o = owners_by_ta.get(ta)
        if o in human:
            amounts[o] = amounts.get(o, 0) + amt
    shares = sorted((amt / total for amt in amounts.values()), reverse=True)
    top10 = round(sum(shares[:10]), 4)
    max_single = round(shares[0], 4) if shares else 0.0
    data = {"top10_share": top10, "max_single": max_single,
            "owners": list(amounts.keys())[:20]}
    pct = f"{top10:.0%}"
    if top10 > TOP10_SHARE_DISQUALIFIER:
        return Finding("holders", DISQUALIFIER,
                       f"Top 10 humans hold {pct} of supply", data)
    if top10 > TOP10_SHARE_WARNING:
        return Finding("holders", WARNING,
                       f"Top 10 humans hold {pct} of supply", data)
    if max_single > SINGLE_HOLDER_WARNING:
        return Finding("holders", WARNING,
                       f"One wallet holds {max_single:.0%} of supply", data)
    return Finding("holders", PASS,
                   f"Supply dispersed — top 10 humans hold {pct}", data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_check_authorities.py tests/test_check_holders.py -v`
Expected: 6 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/checks/ tests/test_check_authorities.py tests/test_check_holders.py
git commit -m "feat: authorities and holder-concentration checks"
```

---

### Task 8: Checks — bundles + dev_record

**Files:**
- Create: `arena/checks/bundles.py`, `arena/checks/dev_record.py`
- Test: `tests/test_check_bundles.py`, `tests/test_check_dev_record.py`

**Interfaces:**
- Same `run(rpc, store, mint, birth, pair) -> Finding` signature as Task 7.
- `bundles.run`: uses `birth.first_txs` (raise `FeatureUnavailable("needs Helius key (Settings)")` if empty AND `rpc.mode == "public"`; if empty in full mode return INFO "launch history unavailable"). Consider txs whose `timestamp` ≤ `birth.created_ts + LAUNCH_WINDOW_S`. A "buyer" = `toUserAccount` of a tokenTransfer with `mint == mint`. Group buyers by tx `slot`; max distinct buyers in one slot drives severity per thresholds. `data` = `{"max_buyers_one_slot": int, "launch_buyers": int}`.
- `dev_record.run`: needs `birth.creator` (if None → INFO "creator unknown"). Full mode only (public → the orchestrator never reaches it because `rpc.enhanced_txs` raises FeatureUnavailable — let it propagate). Fetch `rpc.enhanced_txs(creator, limit=DEV_HISTORY_SAMPLE)`; count prior creations = txs with `type == "TOKEN_MINT"` or (`source == "PUMP_FUN"` and `type == "CREATE"`), excluding any tx whose tokenTransfers reference the current mint. Severity per thresholds. Evidence "Dev launched N prior tokens (sample of last 100 txs)". `data` = `{"prior_launches": int, "creator": creator}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_check_bundles.py`:
```python
import pytest

from arena.birth import Birth
from arena.checks import bundles
from arena.models import DISQUALIFIER, INFO, PASS, WARNING
from arena.rpc import FeatureUnavailable, RpcClient
from tests.helpers import make_client

MINT = "MintX"


def tx(sig, slot, ts, buyers):
    return {"signature": sig, "slot": slot, "timestamp": ts,
            "tokenTransfers": [
                {"mint": MINT, "toUserAccount": b, "fromUserAccount": "pool"}
                for b in buyers]}


def birth_with(txs):
    return Birth(creation_sig="s0", creator="Dev", created_ts=100,
                 first_sig_infos=[], first_txs=txs)


async def test_eight_buyers_one_slot_disqualifies():
    txs = [tx(f"s{i}", 10, 101, [f"B{i}"]) for i in range(8)]
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with(txs), None)
    assert f.severity == DISQUALIFIER and f.data["max_buyers_one_slot"] == 8


async def test_four_buyers_one_slot_warns():
    txs = [tx(f"s{i}", 10, 101, [f"B{i}"]) for i in range(4)]
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with(txs), None)
    assert f.severity == WARNING


async def test_spread_buys_pass_and_window_respected():
    txs = [tx(f"s{i}", 10 + i, 101, [f"B{i}"]) for i in range(3)]
    txs += [tx("late", 99, 500, ["Late1", "Late2", "Late3", "Late4", "Late5"])]
    async with make_client() as c:  # late tx outside 60s window: ignored
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with(txs), None)
    assert f.severity == PASS


async def test_public_mode_raises_feature_unavailable():
    async with make_client() as c:
        with pytest.raises(FeatureUnavailable):
            await bundles.run(RpcClient(c, None), None, MINT, birth_with([]), None)


async def test_full_mode_no_history_is_info():
    async with make_client() as c:
        f = await bundles.run(RpcClient(c, "k"), None, MINT, birth_with([]), None)
    assert f.severity == INFO
```

`tests/test_check_dev_record.py`:
```python
from arena.birth import Birth
from arena.checks import dev_record
from arena.models import DISQUALIFIER, INFO, PASS, WARNING
from arena.rpc import RpcClient
from tests.helpers import make_client


def creation(sig, source="PUMP_FUN", tx_type="CREATE", mint="OldMint"):
    return {"signature": sig, "type": tx_type, "source": source,
            "tokenTransfers": [{"mint": mint}]}


async def test_serial_launcher_disqualifies():
    history = [creation(f"c{i}") for i in range(9)]
    async with make_client(enhanced={"Dev": history}) as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "NewMint",
                                 Birth(creator="Dev"), None)
    assert f.severity == DISQUALIFIER and f.data["prior_launches"] == 9


async def test_three_launches_warns():
    history = [creation(f"c{i}") for i in range(3)] + [
        {"signature": "x", "type": "SWAP", "source": "RAYDIUM", "tokenTransfers": []}]
    async with make_client(enhanced={"Dev": history}) as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "NewMint",
                                 Birth(creator="Dev"), None)
    assert f.severity == WARNING and f.data["prior_launches"] == 3


async def test_current_mint_excluded_and_clean_dev_passes():
    history = [creation("c0", mint="NewMint")]  # only the current launch
    async with make_client(enhanced={"Dev": history}) as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "NewMint",
                                 Birth(creator="Dev"), None)
    assert f.severity == PASS and f.data["prior_launches"] == 0


async def test_unknown_creator_is_info():
    async with make_client() as c:
        f = await dev_record.run(RpcClient(c, "k"), None, "M", Birth(), None)
    assert f.severity == INFO
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_check_bundles.py tests/test_check_dev_record.py -v`
Expected: FAIL, `ImportError`.

- [ ] **Step 3: Implement**

`arena/checks/bundles.py`:
```python
from collections import defaultdict

from arena.birth import Birth
from arena.models import DISQUALIFIER, INFO, PASS, WARNING, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient
from arena.thresholds import (BUNDLE_BUYERS_DISQUALIFIER, BUNDLE_BUYERS_WARNING,
                              LAUNCH_WINDOW_S)


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    if not birth.first_txs:
        if rpc.mode == "public":
            raise FeatureUnavailable("needs Helius key (Settings)")
        return Finding("bundles", INFO, "Launch history unavailable", {})
    cutoff = (birth.created_ts or 0) + LAUNCH_WINDOW_S
    buyers_by_slot: dict[int, set] = defaultdict(set)
    all_buyers: set = set()
    for tx in birth.first_txs:
        if (tx.get("timestamp") or 0) > cutoff:
            continue
        for t in tx.get("tokenTransfers") or []:
            if t.get("mint") == mint and t.get("toUserAccount"):
                buyers_by_slot[tx.get("slot", 0)].add(t["toUserAccount"])
                all_buyers.add(t["toUserAccount"])
    worst = max((len(b) for b in buyers_by_slot.values()), default=0)
    data = {"max_buyers_one_slot": worst, "launch_buyers": len(all_buyers)}
    msg = f"{worst} wallets bought in the same block at launch"
    if worst >= BUNDLE_BUYERS_DISQUALIFIER:
        return Finding("bundles", DISQUALIFIER, msg, data)
    if worst >= BUNDLE_BUYERS_WARNING:
        return Finding("bundles", WARNING, msg, data)
    return Finding("bundles", PASS,
                   f"No bundling — {len(all_buyers)} distinct launch buyers", data)
```

`arena/checks/dev_record.py`:
```python
from arena.birth import Birth
from arena.models import DISQUALIFIER, INFO, PASS, WARNING, Finding
from arena.prices import PairInfo
from arena.rpc import RpcClient
from arena.thresholds import (DEV_HISTORY_SAMPLE, DEV_LAUNCHES_DISQUALIFIER,
                              DEV_LAUNCHES_WARNING)


def _is_creation(tx: dict) -> bool:
    return tx.get("type") == "TOKEN_MINT" or (
        tx.get("source") == "PUMP_FUN" and tx.get("type") == "CREATE")


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    if not birth.creator:
        return Finding("dev_record", INFO, "Creator wallet unknown", {})
    history = await rpc.enhanced_txs(birth.creator, limit=DEV_HISTORY_SAMPLE)
    prior = 0
    for tx in history:
        if not _is_creation(tx):
            continue
        mints = {t.get("mint") for t in tx.get("tokenTransfers") or []}
        if mint not in mints:
            prior += 1
    data = {"prior_launches": prior, "creator": birth.creator}
    msg = f"Dev launched {prior} prior tokens (sample of last {DEV_HISTORY_SAMPLE} txs)"
    if prior >= DEV_LAUNCHES_DISQUALIFIER:
        return Finding("dev_record", DISQUALIFIER, msg, data)
    if prior >= DEV_LAUNCHES_WARNING:
        return Finding("dev_record", WARNING, msg, data)
    return Finding("dev_record", PASS, msg if prior else "No prior launches found", data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_check_bundles.py tests/test_check_dev_record.py -v`
Expected: 9 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/checks/bundles.py arena/checks/dev_record.py tests/test_check_bundles.py tests/test_check_dev_record.py
git commit -m "feat: bundle-detection and dev-record checks"
```

---

### Task 9: Checks — funding + vitals + orchestrator

**Files:**
- Create: `arena/checks/funding.py`, `arena/checks/vitals.py`
- Modify: `arena/checks/__init__.py` (add `run_all_checks`)
- Test: `tests/test_check_funding.py`, `tests/test_check_vitals.py`, `tests/test_run_all.py`

**Interfaces:**
- `funding.run`: needs `birth.creator` (None → INFO "creator unknown"). `getSignaturesForAddress(creator, {limit: 1000})`; if 1000 returned → INFO "Creator wallet too active to trace funding cheaply" (`data={"funder": None}`). Else oldest signature → full mode: `enhanced_batch([sig])`, funder = first `nativeTransfers` entry's `fromUserAccount` where `toUserAccount == creator`; public mode: raise `FeatureUnavailable`. With funder found: `store.funder_rugged_count(funder)` ≥1 → DISQUALIFIER "Funded by wallet that funded N rugged coins"; else PASS "Funder has no rug history in your database". Always `data={"funder": funder}` when found.
- `vitals.run`: always returns INFO (never affects verdict). Composes: age from `birth.created_ts` ("age 3m 41s" style, minutes+seconds under 1h, hours over); holder count via `rpc.das("getTokenAccounts", {"mint": mint, "limit": 1000, "page": 1})` → `len(result["token_accounts"])`, shown "1000+" at cap, skipped in public mode (FeatureUnavailable caught INSIDE vitals — vitals is the one check that partially degrades rather than failing); liquidity from `pair.liquidity_usd`; smart-money line via `store.survivor_wallet_count(top holder owners)` — holders' owners are not available to vitals (checks are independent), so vitals recomputes nothing: smart-money count is computed in Task 10's engine from the holders finding's data and appended there. Vitals `data` = `{"age_s": int|None, "holder_count": int|None, "liquidity_usd": float|None}`.
- `run_all_checks(rpc, store, mint, birth, pair) -> list[Finding]` in `arena/checks/__init__.py`: runs all six `run` coroutines via `asyncio.gather(..., return_exceptions=True)` with `asyncio.wait_for(..., CHECK_TIMEOUT_S)` each. Exception mapping: `FeatureUnavailable` → INFO with its message; `TimeoutError` → INFO "check unavailable (timeout)"; any other exception → INFO "check unavailable" with `redact(str(exc))` appended, logged via `logging`. Findings returned in fixed order: authorities, holders, bundles, dev_record, funding, vitals.

- [ ] **Step 1: Write the failing tests**

`tests/test_check_funding.py`:
```python
from arena.birth import Birth
from arena.checks import funding
from arena.models import DISQUALIFIER, INFO, PASS
from arena.rpc import RpcClient
from arena.store import Store
from tests.helpers import make_client

B = Birth(creator="Dev")
FUND_TX = {"__by_sig__": {"f1": {"signature": "f1", "nativeTransfers": [
    {"fromUserAccount": "Funder1", "toUserAccount": "Dev", "amount": 5000000}]}}}
SIGS = [{"signature": "f2"}, {"signature": "f1"}]  # newest-first; f1 = oldest


async def test_known_rugger_funder_disqualifies(tmp_path):
    store = Store(tmp_path / "a.db")
    from arena.models import Finding, ScanResult
    store.save_scan(ScanResult("OldRug", "AVOID", [], 0, None, None, 0),
                    creator=None, funder="Funder1", top_holders=[])
    store.record_outcome("OldRug", "RUGGED")
    async with make_client({"getSignaturesForAddress": SIGS}, enhanced=FUND_TX) as c:
        f = await funding.run(RpcClient(c, "k"), store, "M", B, None)
    assert f.severity == DISQUALIFIER and f.data["funder"] == "Funder1"


async def test_clean_funder_passes(tmp_path):
    store = Store(tmp_path / "a.db")
    async with make_client({"getSignaturesForAddress": SIGS}, enhanced=FUND_TX) as c:
        f = await funding.run(RpcClient(c, "k"), store, "M", B, None)
    assert f.severity == PASS and f.data["funder"] == "Funder1"


async def test_busy_wallet_is_info(tmp_path):
    store = Store(tmp_path / "a.db")
    sigs = [{"signature": f"s{i}"} for i in range(1000)]
    async with make_client({"getSignaturesForAddress": sigs}) as c:
        f = await funding.run(RpcClient(c, "k"), store, "M", B, None)
    assert f.severity == INFO and "too active" in f.evidence
```

`tests/test_check_vitals.py`:
```python
import time

from arena.birth import Birth
from arena.checks import vitals
from arena.models import INFO
from arena.prices import PairInfo
from arena.rpc import RpcClient
from tests.helpers import make_client


async def test_vitals_full_mode():
    das = {"getTokenAccounts": {"token_accounts": [{"address": f"a{i}"} for i in range(42)]}}
    birth = Birth(created_ts=int(time.time()) - 221)
    pair = PairInfo(price_usd=0.01, liquidity_usd=12345.0, symbol="T")
    async with make_client(das) as c:
        f = await vitals.run(RpcClient(c, "k"), None, "M", birth, pair)
    assert f.severity == INFO
    assert f.data["holder_count"] == 42 and f.data["liquidity_usd"] == 12345.0
    assert 200 <= f.data["age_s"] <= 240


async def test_vitals_public_mode_degrades_gracefully():
    async with make_client() as c:  # DAS would raise FeatureUnavailable
        f = await vitals.run(RpcClient(c, None), None, "M", Birth(), None)
    assert f.severity == INFO and f.data["holder_count"] is None
```

`tests/test_run_all.py`:
```python
from arena.birth import Birth
from arena.checks import run_all_checks
from arena.models import CHECK_NAMES, INFO
from arena.rpc import RpcClient
from arena.store import Store
from tests.helpers import make_client


async def test_public_mode_never_raises_and_orders_findings(tmp_path):
    store = Store(tmp_path / "a.db")
    m = {"getSignaturesForAddress": [], "getAccountInfo": 500,
         "getTokenLargestAccounts": 500, "getTokenSupply": 500}
    async with make_client(m) as c:  # everything fails or is keyless
        findings = await run_all_checks(RpcClient(c, None), store, "M", Birth(), None)
    assert [f.check for f in findings] == CHECK_NAMES
    assert all(f.severity == INFO for f in findings[:5])  # vitals also INFO
    assert any("needs Helius key" in f.evidence for f in findings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_check_funding.py tests/test_check_vitals.py tests/test_run_all.py -v`
Expected: FAIL, `ImportError`.

- [ ] **Step 3: Implement**

`arena/checks/funding.py`:
```python
from arena.birth import Birth
from arena.models import DISQUALIFIER, INFO, PASS, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient
from arena.thresholds import FUNDING_MAX_SIGS


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    if not birth.creator:
        return Finding("funding", INFO, "Creator wallet unknown", {"funder": None})
    sigs = await rpc.rpc("getSignaturesForAddress",
                         [birth.creator, {"limit": FUNDING_MAX_SIGS}])
    if len(sigs) >= FUNDING_MAX_SIGS:
        return Finding("funding", INFO,
                       "Creator wallet too active to trace funding cheaply",
                       {"funder": None})
    if not sigs:
        return Finding("funding", INFO, "Creator wallet has no history",
                       {"funder": None})
    if rpc.mode == "public":
        raise FeatureUnavailable("needs Helius key (Settings)")
    oldest = sigs[-1]["signature"]
    txs = await rpc.enhanced_batch([oldest])
    funder = None
    for t in (txs[0].get("nativeTransfers") or []) if txs else []:
        if t.get("toUserAccount") == birth.creator and t.get("fromUserAccount"):
            funder = t["fromUserAccount"]
            break
    if not funder:
        return Finding("funding", INFO, "Could not identify funder",
                       {"funder": None})
    rugs = store.funder_rugged_count(funder)
    data = {"funder": funder}
    if rugs >= 1:
        return Finding("funding", DISQUALIFIER,
                       f"Funded by wallet that funded {rugs} rugged coin(s)", data)
    return Finding("funding", PASS,
                   "Funder has no rug history in your database", data)
```

`arena/checks/vitals.py`:
```python
import time

from arena.birth import Birth
from arena.models import INFO, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient, RpcError


def _fmt_age(age_s: int) -> str:
    if age_s < 3600:
        return f"{age_s // 60}m {age_s % 60}s"
    return f"{age_s // 3600}h {(age_s % 3600) // 60}m"


async def run(rpc: RpcClient, store, mint: str, birth: Birth,
              pair: PairInfo | None) -> Finding:
    age_s = int(time.time()) - birth.created_ts if birth.created_ts else None
    holder_count = None
    try:
        das = await rpc.das("getTokenAccounts", {"mint": mint, "limit": 1000, "page": 1})
        holder_count = len(das.get("token_accounts") or [])
    except (FeatureUnavailable, RpcError):
        pass  # vitals degrades, never fails
    liq = pair.liquidity_usd if pair else None
    bits = []
    if age_s is not None:
        bits.append(f"age {_fmt_age(age_s)}")
    if holder_count is not None:
        bits.append(f"{'1000+' if holder_count >= 1000 else holder_count} holders")
    bits.append(f"liquidity ${liq:,.0f}" if liq is not None else "no DEX pair yet")
    return Finding("vitals", INFO, " · ".join(bits),
                   {"age_s": age_s, "holder_count": holder_count,
                    "liquidity_usd": liq})
```

`arena/checks/__init__.py`:
```python
import asyncio
import logging

from arena.birth import Birth
from arena.checks import (authorities, bundles, dev_record, funding, holders,
                          vitals)
from arena.models import INFO, Finding
from arena.prices import PairInfo
from arena.rpc import FeatureUnavailable, RpcClient, redact
from arena.store import Store
from arena.thresholds import CHECK_TIMEOUT_S

log = logging.getLogger(__name__)

_CHECKS = [("authorities", authorities), ("holders", holders),
           ("bundles", bundles), ("dev_record", dev_record),
           ("funding", funding), ("vitals", vitals)]


async def run_all_checks(rpc: RpcClient, store: Store, mint: str, birth: Birth,
                         pair: PairInfo | None) -> list[Finding]:
    async def guarded(name, module) -> Finding:
        try:
            return await asyncio.wait_for(
                module.run(rpc, store, mint, birth, pair), CHECK_TIMEOUT_S)
        except FeatureUnavailable as exc:
            return Finding(name, INFO, str(exc), {})
        except asyncio.TimeoutError:
            return Finding(name, INFO, "check unavailable (timeout)", {})
        except Exception as exc:
            log.warning("check %s failed: %s", name, redact(str(exc)))
            return Finding(name, INFO,
                           f"check unavailable ({redact(str(exc))[:80]})", {})

    return list(await asyncio.gather(*(guarded(n, m) for n, m in _CHECKS)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_check_funding.py tests/test_check_vitals.py tests/test_run_all.py -v`
Expected: 6 PASSED. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add arena/checks/ tests/test_check_funding.py tests/test_check_vitals.py tests/test_run_all.py
git commit -m "feat: funding and vitals checks plus crash-proof orchestrator"
```

---

### Task 10: Engine + CLI `check` / `set-key`

**Files:**
- Create: `arena/engine.py`, `arena/__main__.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: everything above, exact signatures as defined.
- Produces:
  ```python
  # arena/engine.py
  MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
  async def check_mint(mint: str, settings: Settings, store: Store,
                       client: httpx.AsyncClient) -> ScanResult
      # raises ValueError("not a valid Solana mint address") on bad input
  ```
  Engine flow: validate → `RpcClient` → `fetch_birth` and `fetch_pair` concurrently → `run_all_checks` → smart-money append: `store.survivor_wallet_count(holders_finding.data.get("owners", []))` → if >0, append to the vitals finding's evidence (" · N top holders have winning history") and set `data["smart_money"]` — else `data["smart_money"] = 0` silently → `verdict(findings)` → `unavailable` = count of findings with severity INFO and evidence containing "unavailable" or "needs Helius key" → build ScanResult (symbol/price from pair) → `store.save_scan(result, creator=birth.creator, funder=funding_finding.data.get("funder"), top_holders=holders_finding.data.get("owners", []))` → return. `duration_s` measured with `time.monotonic()`.
- CLI (`python -m arena`): argparse subcommands. `check <mint>` — rich output: verdict banner (red/yellow/green panel; green panel includes caption "no red flags ≠ safe"), then one line per finding (severity-colored), then footer `N of 6 checks unavailable — public mode` when applicable. Exit code 0 always (it's information, not CI). `set-key <key>` — calls `save_key`, then makes one `getSlot` call via a fresh RpcClient to validate; prints "key saved (validated)" or "key saved (validation failed: <redacted>)".

- [ ] **Step 1: Write the failing tests**

`tests/test_engine.py`:
```python
import pytest

from arena.engine import check_mint
from arena.settings import Settings
from arena.store import Store
from tests.helpers import make_client

GOOD_MINT = "6dkGZgkn8Togra9BJeZkyAtZAGxNEQUF7sVzY8Tqpump"
SYSTEM = "11111111111111111111111111111111"

CLEAN_RPC = {
    "getAccountInfo": {"value": {"data": {"parsed": {"info": {
        "mintAuthority": None, "freezeAuthority": None}}}}},
    "getTokenLargestAccounts": {"value": [{"address": "TA0", "uiAmount": 10.0}]},
    "getTokenSupply": {"value": {"uiAmount": 1000.0}},
    "getMultipleAccounts": lambda params: (
        {"value": [{"data": {"parsed": {"info": {"owner": "W1"}}}}]}
        if params[0][0].startswith("TA") else {"value": [{"owner": SYSTEM}]}),
    "getSignaturesForAddress": [{"signature": "s1", "slot": 1, "blockTime": 100}],
    "getTokenAccounts": {"token_accounts": []},
}
ENHANCED = {"__by_sig__": {"s1": {"signature": "s1", "feePayer": "Dev",
                                  "slot": 1, "timestamp": 100,
                                  "tokenTransfers": [], "nativeTransfers": []}},
            "Dev": []}
DS = {GOOD_MINT: {"pairs": [{"priceUsd": "0.002", "liquidity": {"usd": 5000},
                             "baseToken": {"symbol": "TEST"}}]}}


async def test_invalid_mint_raises_valueerror(tmp_path):
    store = Store(tmp_path / "a.db")
    async with make_client() as c:
        with pytest.raises(ValueError):
            await check_mint("not-a-mint!!", Settings("k"), store, c)


async def test_clean_coin_end_to_end(tmp_path):
    store = Store(tmp_path / "a.db")
    async with make_client(CLEAN_RPC, enhanced=ENHANCED, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.verdict == "NO_RED_FLAGS"
    assert r.symbol == "TEST" and r.price_usd == 0.002
    assert len(r.findings) == 6
    assert store.recent_scans()[0]["mint"] == GOOD_MINT


async def test_rug_pattern_is_avoid(tmp_path):
    rug_rpc = dict(CLEAN_RPC)
    rug_rpc["getAccountInfo"] = {"value": {"data": {"parsed": {"info": {
        "mintAuthority": "Dev", "freezeAuthority": None}}}}}
    store = Store(tmp_path / "a.db")
    async with make_client(rug_rpc, enhanced=ENHANCED, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings("k"), store, c)
    assert r.verdict == "AVOID"


async def test_public_mode_still_scans(tmp_path):
    store = Store(tmp_path / "a.db")
    public_rpc = dict(CLEAN_RPC)
    public_rpc["getTransaction"] = {"transaction": {"message": {"accountKeys": [
        {"pubkey": "Dev"}]}}}
    async with make_client(public_rpc, dexscreener=DS) as c:
        r = await check_mint(GOOD_MINT, Settings(None), store, c)
    assert r.verdict in ("NO_RED_FLAGS", "CAUTION")
    assert r.unavailable >= 2  # bundles, dev_record at minimum
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_engine.py -v` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`arena/engine.py`:
```python
import asyncio
import re
import time

import httpx

from arena.birth import fetch_birth
from arena.checks import run_all_checks
from arena.models import INFO, ScanResult
from arena.prices import fetch_pair
from arena.rpc import RpcClient
from arena.scoring import verdict
from arena.settings import Settings
from arena.store import Store

MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


async def check_mint(mint: str, settings: Settings, store: Store,
                     client: httpx.AsyncClient) -> ScanResult:
    if not MINT_RE.match(mint):
        raise ValueError("not a valid Solana mint address")
    start = time.monotonic()
    rpc = RpcClient(client, settings.helius_key)
    birth, pair = await asyncio.gather(fetch_birth(rpc, mint),
                                       fetch_pair(client, mint))
    findings = await run_all_checks(rpc, store, mint, birth, pair)
    by_check = {f.check: f for f in findings}

    owners = by_check["holders"].data.get("owners", [])
    smart = store.survivor_wallet_count(owners) if owners else 0
    by_check["vitals"].data["smart_money"] = smart
    if smart:
        by_check["vitals"].evidence += f" · {smart} top holders have winning history"

    unavailable = sum(1 for f in findings if f.severity == INFO and
                      ("unavailable" in f.evidence or "needs Helius key" in f.evidence))
    result = ScanResult(
        mint=mint, verdict=verdict(findings), findings=findings,
        unavailable=unavailable,
        price_usd=pair.price_usd if pair else None,
        symbol=pair.symbol if pair else None,
        duration_s=round(time.monotonic() - start, 2))
    store.save_scan(result, creator=birth.creator,
                    funder=by_check["funding"].data.get("funder"),
                    top_holders=owners)
    return result
```

`arena/__main__.py` (check + set-key only; Task 11 adds verify/report):
```python
import argparse
import asyncio

import httpx
from rich.console import Console
from rich.panel import Panel

from arena.engine import check_mint
from arena.models import DISQUALIFIER, INFO, WARNING
from arena.rpc import RpcClient, RpcError, redact
from arena.settings import load_settings, save_key
from arena.store import Store

console = Console()

BANNERS = {
    "AVOID": ("🔴 AVOID", "red"),
    "CAUTION": ("🟡 CAUTION", "yellow"),
    "NO_RED_FLAGS": ("🟢 NO RED FLAGS — no red flags ≠ safe", "green"),
}
SEV_STYLE = {DISQUALIFIER: "bold red", WARNING: "yellow", INFO: "dim"}


def print_result(r) -> None:
    label, color = BANNERS[r.verdict]
    sub = f"{r.symbol or r.mint[:8] + '…'} · scanned in {r.duration_s}s"
    console.print(Panel(f"[bold]{label}[/bold]\n{sub}", border_style=color))
    for f in r.findings:
        style = SEV_STYLE.get(f.severity, "")
        console.print(f"  {f.severity:<13} {f.evidence}", style=style)
    if r.unavailable:
        console.print(f"\n[dim]{r.unavailable} of 6 checks unavailable — "
                      "add a free Helius key with: python -m arena set-key <key>[/dim]")


async def cmd_check(mint: str) -> None:
    settings = load_settings()
    store = Store()
    async with httpx.AsyncClient() as client:
        try:
            result = await check_mint(mint, settings, store, client)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return
    print_result(result)
    store.close()


async def cmd_set_key(key: str) -> None:
    save_key(key)
    async with httpx.AsyncClient() as client:
        try:
            await RpcClient(client, key).rpc("getSlot", [])
            console.print("key saved (validated)")
        except RpcError as exc:
            console.print(f"key saved (validation failed: {redact(str(exc))})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="arena",
                                     description="Coin Arena — pre-buy rug checks")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="scan a mint address")
    p_check.add_argument("mint")
    p_key = sub.add_parser("set-key", help="save your free Helius API key")
    p_key.add_argument("key")
    args = parser.parse_args()
    if args.command == "check":
        asyncio.run(cmd_check(args.mint))
    elif args.command == "set-key":
        asyncio.run(cmd_set_key(args.key))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_engine.py -v` — Expected: 4 PASSED. Full suite green.

- [ ] **Step 5: Manual smoke (real network, uses your key if HELIUS_API_KEY set or saved)**

```bash
.venv/bin/python -m arena check 6dkGZgkn8Togra9BJeZkyAtZAGxNEQUF7sVzY8Tqpump
```
Expected: verdict panel + six finding lines in <15s. (This mint may be long dead — INFO-heavy output is fine; the point is no crash and sane output.)

- [ ] **Step 6: Commit**

```bash
git add arena/engine.py arena/__main__.py tests/test_engine.py
git commit -m "feat: scan engine and CLI check/set-key commands"
```

---

### Task 11: Verify + report + CLI wiring + README + live test

**Files:**
- Create: `arena/verify.py`, `arena/report.py`, `tests/test_verify.py`, `tests/test_report.py`, `tests/test_live.py`, `README.md`
- Modify: `arena/__main__.py` (add `verify` and `report` subcommands)

**Interfaces:**
- `arena/verify.py`:
  ```python
  async def verify_outcomes(client: httpx.AsyncClient, store: Store,
                            now: int | None = None) -> list[tuple[str, str]]
  ```
  For each `store.unverified_scans(now - VERIFY_MIN_AGE_S)`: `fetch_pair` → outcome: pair None or `liquidity_usd < DEAD_LIQUIDITY_USD` → `DEAD`; elif scan had `price_usd_at_scan` and `pair.price_usd <= RUG_PRICE_RATIO * price_usd_at_scan` → `RUGGED`; else `ALIVE`. Calls `store.record_outcome`, returns list of (mint, outcome).
- `arena/report.py`:
  ```python
  def flag_hit_rates(store: Store) -> list[dict]
      # per check name: {"check", "fired_bad", "fired_total", "quiet_bad", "quiet_total"}
      # fired = severity in (WARNING, DISQUALIFIER) in that scan; bad = outcome in (RUGGED, DEAD)
  ```
- CLI: `python -m arena verify` prints each labeled coin + summary count; `python -m arena report` prints a rich table: check, "fired → bad" as `X/Y (Z%)`, "quiet → bad" as `X/Y (Z%)`; footer note "hit rates need ~300 verified scans to mean much — keep scanning".

- [ ] **Step 1: Write the failing tests**

`tests/test_verify.py`:
```python
import time

from arena.models import Finding, ScanResult
from arena.store import Store
from arena.verify import verify_outcomes
from tests.helpers import make_client


def seed(store, mint, price):
    store.save_scan(ScanResult(mint, "NO_RED_FLAGS",
                    [Finding("authorities", "PASS", "e", {})], 0, price, "T", 1.0),
                    None, None, [])
    store.conn.execute("UPDATE scans SET ts = ? WHERE mint = ?",
                       (int(time.time()) - 100000, mint))
    store.conn.commit()


async def test_labels_dead_rugged_alive(tmp_path):
    store = Store(tmp_path / "a.db")
    seed(store, "MintDead", 1.0)
    seed(store, "MintRug", 1.0)
    seed(store, "MintOk", 1.0)
    ds = {
        "MintDead": {"pairs": None},
        "MintRug": {"pairs": [{"priceUsd": "0.05", "liquidity": {"usd": 5000},
                               "baseToken": {"symbol": "R"}}]},
        "MintOk": {"pairs": [{"priceUsd": "2.0", "liquidity": {"usd": 9000},
                              "baseToken": {"symbol": "O"}}]},
    }
    async with make_client(dexscreener=ds) as c:
        labeled = dict(await verify_outcomes(c, store))
    assert labeled == {"MintDead": "DEAD", "MintRug": "RUGGED", "MintOk": "ALIVE"}
    assert store.unverified_scans(2**62) == []


async def test_fresh_scans_not_verified_yet(tmp_path):
    store = Store(tmp_path / "a.db")
    store.save_scan(ScanResult("MintNew", "NO_RED_FLAGS", [], 0, 1.0, "T", 1.0),
                    None, None, [])
    async with make_client() as c:
        assert await verify_outcomes(c, store) == []
```

`tests/test_report.py`:
```python
from arena.models import Finding, ScanResult
from arena.report import flag_hit_rates
from arena.store import Store


def scan_with(store, mint, sev):
    store.save_scan(ScanResult(mint, "AVOID",
                    [Finding("dev_record", sev, "e", {})], 0, 1.0, "T", 1.0),
                    None, None, [])


def test_hit_rates(tmp_path):
    store = Store(tmp_path / "a.db")
    scan_with(store, "M1", "DISQUALIFIER"); store.record_outcome("M1", "RUGGED")
    scan_with(store, "M2", "DISQUALIFIER"); store.record_outcome("M2", "ALIVE")
    scan_with(store, "M3", "PASS");        store.record_outcome("M3", "ALIVE")
    rows = {r["check"]: r for r in flag_hit_rates(store)}
    dev = rows["dev_record"]
    assert dev["fired_total"] == 2 and dev["fired_bad"] == 1
    assert dev["quiet_total"] == 1 and dev["quiet_bad"] == 0
```

`tests/test_live.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_verify.py tests/test_report.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`arena/verify.py`:
```python
import time

import httpx

from arena.prices import fetch_pair
from arena.store import Store
from arena.thresholds import DEAD_LIQUIDITY_USD, RUG_PRICE_RATIO, VERIFY_MIN_AGE_S


async def verify_outcomes(client: httpx.AsyncClient, store: Store,
                          now: int | None = None) -> list[tuple[str, str]]:
    now = now or int(time.time())
    labeled: list[tuple[str, str]] = []
    for row in store.unverified_scans(now - VERIFY_MIN_AGE_S):
        pair = await fetch_pair(client, row["mint"])
        if pair is None or (pair.liquidity_usd or 0) < DEAD_LIQUIDITY_USD:
            outcome = "DEAD"
        elif (row["price_usd_at_scan"] and pair.price_usd is not None
              and pair.price_usd <= RUG_PRICE_RATIO * row["price_usd_at_scan"]):
            outcome = "RUGGED"
        else:
            outcome = "ALIVE"
        store.record_outcome(row["mint"], outcome)
        labeled.append((row["mint"], outcome))
    return labeled
```

`arena/report.py`:
```python
import json

from arena.models import CHECK_NAMES, DISQUALIFIER, WARNING
from arena.store import Store

BAD = ("RUGGED", "DEAD")


def flag_hit_rates(store: Store) -> list[dict]:
    stats = {c: {"check": c, "fired_bad": 0, "fired_total": 0,
                 "quiet_bad": 0, "quiet_total": 0} for c in CHECK_NAMES}
    for row in store.scans_with_outcomes():
        bad = row["outcome"] in BAD
        by_check = {f["check"]: f for f in json.loads(row["scan_json"])}
        for name in CHECK_NAMES:
            f = by_check.get(name)
            if f is None:
                continue
            fired = f["severity"] in (WARNING, DISQUALIFIER)
            bucket = "fired" if fired else "quiet"
            stats[name][f"{bucket}_total"] += 1
            if bad:
                stats[name][f"{bucket}_bad"] += 1
    return [s for s in stats.values() if s["fired_total"] or s["quiet_total"]]
```

Modify `arena/__main__.py` — add imports and subcommands (full new `main()` shown; replace the old one, keep `cmd_check`/`cmd_set_key`/`print_result` as-is):
```python
from rich.table import Table

from arena.report import flag_hit_rates
from arena.verify import verify_outcomes


async def cmd_verify() -> None:
    store = Store()
    async with httpx.AsyncClient() as client:
        labeled = await verify_outcomes(client, store)
    for mint, outcome in labeled:
        console.print(f"  {mint[:10]}…  {outcome}")
    console.print(f"{len(labeled)} coin(s) labeled.")
    store.close()


def cmd_report() -> None:
    store = Store()
    rows = flag_hit_rates(store)
    if not rows:
        console.print("No verified scans yet — run some checks, then "
                      "'verify' after 24h.")
        store.close()
        return
    table = Table(title="Per-flag hit rates (bad = rugged or dead)")
    table.add_column("check"); table.add_column("fired → bad")
    table.add_column("quiet → bad")
    for r in rows:
        def cell(bad, total):
            return f"{bad}/{total} ({bad / total:.0%})" if total else "—"
        table.add_row(r["check"], cell(r["fired_bad"], r["fired_total"]),
                      cell(r["quiet_bad"], r["quiet_total"]))
    console.print(table)
    console.print("[dim]hit rates need ~300 verified scans to mean much — "
                  "keep scanning[/dim]")
    store.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="arena",
                                     description="Coin Arena — pre-buy rug checks")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="scan a mint address")
    p_check.add_argument("mint")
    p_key = sub.add_parser("set-key", help="save your free Helius API key")
    p_key.add_argument("key")
    sub.add_parser("verify", help="label outcomes of past scans (24h+)")
    sub.add_parser("report", help="per-flag hit rates from your verified scans")
    args = parser.parse_args()
    if args.command == "check":
        asyncio.run(cmd_check(args.mint))
    elif args.command == "set-key":
        asyncio.run(cmd_set_key(args.key))
    elif args.command == "verify":
        asyncio.run(cmd_verify())
    elif args.command == "report":
        cmd_report()
```

`README.md`:
```markdown
# Coin Arena (engine preview)

Pre-buy rug checks for Solana meme coins. Paste a mint address, get a
verdict in seconds: 🔴 AVOID / 🟡 CAUTION / 🟢 NO RED FLAGS (which is not
the same as safe). Six checks: mint/freeze authorities, holder
concentration, launch bundling, dev history, funding trail, vitals.
Every scan is logged locally; `verify` labels what actually happened;
`report` shows which flags actually predicted rugs in YOUR data.

The desktop app (GUI) is coming; this is the engine + terminal preview.

## Setup

    python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
    .venv/bin/python -m arena set-key YOUR_FREE_HELIUS_KEY   # helius.dev, free

No key? Scans still run in degraded public mode (3 of 6 checks).

## Use

    .venv/bin/python -m arena check <mint address>
    .venv/bin/python -m arena verify     # label past scans (24h+ old)
    .venv/bin/python -m arena report     # per-flag hit rates

## Honest caveats

- This detects *mechanical* rug setups. It cannot detect intent, Twitter
  exit scams, or slow deaths. 🟢 means "no red flags found", never "safe".
- Not financial advice. The tool never trades.

## Tests

    .venv/bin/pytest             # offline, no network
    .venv/bin/pytest -m live -v  # real APIs, needs key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_verify.py tests/test_report.py -v` — Expected: 3 PASSED.
Full suite: `.venv/bin/pytest` — all green, live deselected.
Live capture once: `.venv/bin/pytest -m live -v` — Expected: 1 PASSED (prints the six real findings; if a check's evidence shows "check unavailable" due to real-schema drift, fix the check's field access to match the printed reality and re-run).

- [ ] **Step 5: Commit**

```bash
git add arena/verify.py arena/report.py arena/__main__.py tests/ README.md
git commit -m "feat: outcome verification, hit-rate report, CLI wiring, README"
```

---

## Verification against spec (after all tasks)

1. `.venv/bin/pytest` — green, zero network.
2. `.venv/bin/python -m arena check <fresh pump.fun mint copied from Axiom>` with a real key: six findings, verdict, <15s, no key text anywhere in output.
3. Unset key (`ARENA_DATA_DIR=/tmp/pub python -m arena check <mint>`): still works, INFO rows say "needs Helius key (Settings)".
4. `git log --oneline` — one commit per task; `git status` clean; no `config.json`/`arena.db` tracked.
