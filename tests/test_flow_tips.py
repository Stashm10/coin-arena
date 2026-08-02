import httpx
import pytest

from arena.flow.tips import TipLookupError, fetch_tips, recommend

PAYLOAD = [{
    "time": "2026-08-02T00:51:00+00:00",
    "landed_tips_25th_percentile": 1e-6,
    "landed_tips_50th_percentile": 1e-6,
    "landed_tips_75th_percentile": 1.598e-6,
    "landed_tips_95th_percentile": 0.0005,
    "landed_tips_99th_percentile": 0.00185,
    "ema_landed_tips_50th_percentile": 1.93e-6,
}]


def _client(response):
    def handler(request):
        return response
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_parses_percentiles():
    async with _client(httpx.Response(200, json=PAYLOAD)) as c:
        tips = await fetch_tips(c)
    assert tips.p50 == 1e-6
    assert tips.p95 == 0.0005
    assert tips.p99 == 0.00185


async def test_http_error_raises_lookup_error():
    async with _client(httpx.Response(503)) as c:
        with pytest.raises(TipLookupError):
            await fetch_tips(c)


async def test_empty_list_raises_lookup_error():
    async with _client(httpx.Response(200, json=[])) as c:
        with pytest.raises(TipLookupError):
            await fetch_tips(c)


async def test_missing_field_raises_lookup_error():
    async with _client(httpx.Response(200, json=[{"time": "x"}])) as c:
        with pytest.raises(TipLookupError):
            await fetch_tips(c)


async def test_recommendation_levels_are_ordered():
    async with _client(httpx.Response(200, json=PAYLOAD)) as c:
        tips = await fetch_tips(c)
    assert recommend(tips, "low") <= recommend(tips, "normal") <= recommend(tips, "high")


async def test_unknown_aggressiveness_falls_back_to_p75():
    async with _client(httpx.Response(200, json=PAYLOAD)) as c:
        tips = await fetch_tips(c)
    assert recommend(tips, "nonsense") == tips.p75
