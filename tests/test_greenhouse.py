import json
import pathlib

import httpx
import respx

from jobfinder.adapters.greenhouse import Greenhouse

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "greenhouse_jfrog.json").read_text()
)


@respx.mock
async def test_parses_real_payload():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "jfrog", "JFrog")

    assert len(jobs) == len(FIX["jobs"])
    j = jobs[0]
    assert j.ats == "greenhouse"
    assert j.company == "JFrog"
    assert j.title
    assert j.url.startswith("http")
    assert j.job_id


@respx.mock
async def test_description_is_unescaped_plain_text():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "jfrog", "JFrog")
    body = " ".join(j.description for j in jobs)
    assert "&lt;" not in body
    assert "<p>" not in body


@respx.mock
async def test_finds_israeli_locations():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "jfrog", "JFrog")
    assert any("israel" in j.location.lower() for j in jobs)


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/gone/jobs?content=true"
    ).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        assert await Greenhouse().fetch(c, "gone", "Gone") == []
