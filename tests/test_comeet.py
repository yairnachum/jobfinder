import json
import pathlib

import httpx
import respx

from jobfinder.adapters.comeet import Comeet

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "comeet_cycode.json").read_text()
)
# Comeet identifies a board by a uid AND a public token, carried in the
# registry as one "uid|token" string.
TOKEN = "A8.00D|8AD340E3CBB3CBB22B4456803D1E2E6B"
URL = (
    "https://www.comeet.co/careers-api/2.0/company/A8.00D/positions"
    "?token=8AD340E3CBB3CBB22B4456803D1E2E6B&details=true"
)


@respx.mock
async def test_parses_real_payload():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Comeet().fetch(c, TOKEN, "Cycode")
    assert len(jobs) == len(FIX)
    assert jobs[0].ats == "comeet"
    assert jobs[0].company == "Cycode"


@respx.mock
async def test_uses_iso_country_from_location():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Comeet().fetch(c, TOKEN, "Cycode")
    assert any(j.country == "IL" for j in jobs)


@respx.mock
async def test_description_is_plain_text_from_details():
    """details=true returns HTML sections, so no per-job hydration is needed."""
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Comeet().fetch(c, TOKEN, "Cycode")
    assert any(len(j.description) > 50 for j in jobs)
    assert all("<p>" not in j.description for j in jobs)
    assert Comeet().needs_detail is False


@respx.mock
async def test_links_to_the_public_hosted_page():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Comeet().fetch(c, TOKEN, "Cycode")
    assert all(j.url.startswith("http") for j in jobs)
    assert any("comeet.com/jobs" in j.url for j in jobs)


@respx.mock
async def test_dead_board_returns_empty_list():
    dead = ("https://www.comeet.co/careers-api/2.0/company/X0.000/positions"
            "?token=NOPE&details=true")
    respx.get(dead).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        assert await Comeet().fetch(c, "X0.000|NOPE", "Gone") == []


async def test_malformed_registry_token_is_rejected_cleanly():
    """A registry entry missing the '|' must not raise mid-run."""
    async with httpx.AsyncClient() as c:
        assert await Comeet().fetch(c, "no-separator", "Bad") == []
