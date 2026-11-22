import json
import pathlib

import httpx
import respx

from jobfinder.adapters.lever import Lever

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "lever_walkme.json").read_text()
)
URL = "https://api.lever.co/v0/postings/walkme?mode=json"


@respx.mock
async def test_parses_real_payload():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "walkme", "WalkMe")
    assert len(jobs) == len(FIX)
    assert jobs[0].ats == "lever"


def test_title_comes_from_text_field():
    assert "text" in FIX[0], "Lever stores the title in `text`, not `title`"


@respx.mock
async def test_created_at_is_milliseconds_not_seconds():
    """Lever createdAt is epoch ms. Treating it as seconds lands in the far future."""
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "walkme", "WalkMe")
    dated = [j for j in jobs if j.posted_at]
    assert dated, "fixture should contain at least one dated posting"
    for j in dated:
        assert 2000 <= j.posted_at.year <= 2100, f"bad year {j.posted_at}"
        assert j.posted_at.tzinfo is not None


@respx.mock
async def test_country_is_uppercased_iso():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "walkme", "WalkMe")
    for j in jobs:
        if j.country:
            assert j.country.isupper() and len(j.country) == 2


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get("https://api.lever.co/v0/postings/gone?mode=json").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        assert await Lever().fetch(c, "gone", "Gone") == []
