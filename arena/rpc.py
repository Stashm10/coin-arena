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
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
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
