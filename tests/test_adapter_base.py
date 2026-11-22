import httpx
import pytest
import respx

from jobfinder.adapters.base import fetch_json


@respx.mock
async def test_returns_parsed_json():
    respx.get("https://x.test/j").mock(return_value=httpx.Response(200, json={"ok": 1}))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j") == {"ok": 1}


@respx.mock
async def test_retries_then_succeeds():
    route = respx.get("https://x.test/j").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": 2})]
    )
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=2, backoff=0) == {"ok": 2}
    assert route.call_count == 2


@respx.mock
async def test_returns_none_on_404_without_retrying():
    """A 404 is a dead board, not a transient fault — retrying wastes the run."""
    route = respx.get("https://x.test/j").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=3, backoff=0) is None
    assert route.call_count == 1


@respx.mock
async def test_returns_none_after_exhausting_retries():
    respx.get("https://x.test/j").mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=2, backoff=0) is None


@respx.mock
async def test_returns_none_on_malformed_json():
    respx.get("https://x.test/j").mock(return_value=httpx.Response(200, text="not json"))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=1, backoff=0) is None
