import json
import pathlib

import httpx
import respx

from jobfinder.adapters.ashby import Ashby

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "ashby_lemonade.json").read_text()
)
URL = "https://api.ashbyhq.com/posting-api/job-board/lemonade"


@respx.mock
async def test_parses_real_payload():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "lemonade", "Lemonade")
    assert len(jobs) == len(FIX["jobs"])
    assert jobs[0].ats == "ashby"
    assert jobs[0].company == "Lemonade"


@respx.mock
async def test_extracts_country_from_postal_address():
    """Ashby location is often an abbreviation like 'TLV';
    addressCountry is the reliable signal."""
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "lemonade", "Lemonade")
    assert any(j.country == "IL" for j in jobs)


@respx.mock
async def test_uses_plain_description():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "lemonade", "Lemonade")
    assert any(j.description for j in jobs)
    assert all("<p>" not in j.description for j in jobs)


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/gone").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        assert await Ashby().fetch(c, "gone", "Gone") == []
