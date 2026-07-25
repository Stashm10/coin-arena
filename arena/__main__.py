import argparse
import asyncio

import httpx
from rich.console import Console
from rich.markup import escape
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
    sub = f"{escape(r.symbol) if r.symbol else r.mint[:8] + '…'} · scanned in {r.duration_s}s"
    console.print(Panel(f"[bold]{label}[/bold]\n{sub}", border_style=color))
    for f in r.findings:
        style = SEV_STYLE.get(f.severity, "")
        console.print(f"  {escape(f.severity):<13} {escape(f.evidence)}", style=style)
    if r.unavailable:
        console.print(f"\n[dim]{r.unavailable} of 6 checks unavailable — "
                      "add a free Helius key with: python -m arena set-key <key>[/dim]")


async def cmd_check(mint: str) -> None:
    settings = load_settings()
    store = Store()
    try:
        async with httpx.AsyncClient() as client:
            result = await check_mint(mint, settings, store, client)
        print_result(result)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
    except Exception as exc:
        console.print(f"[red]scan failed:[/red] {redact(str(exc))}")
    finally:
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
