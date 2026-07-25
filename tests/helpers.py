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
            if isinstance(spec, int) and spec >= 400:
                # High ints (4xx/5xx) are HTTP error status codes
                return httpx.Response(spec)
            # Everything else is a result value
            result = spec(body["params"]) if callable(spec) else spec
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
        return httpx.Response(500)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
