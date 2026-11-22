import json
import pathlib

import httpx
import respx

from jobfinder.adapters.workday import Workday

HERE = pathlib.Path(__file__).parent / "fixtures"
LIST = json.loads((HERE / "workday_nvidia.json").read_text())
DETAIL = json.loads((HERE / "workday_nvidia_detail.json").read_text())
TOKEN = "nvidia|wd5|NVIDIAExternalCareerSite"
LIST_URL = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"


@respx.mock
async def test_parses_listing():
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await Workday().fetch(c, TOKEN, "NVIDIA")
    assert jobs and jobs[0].ats == "workday"
    assert jobs[0].company == "NVIDIA"


@respx.mock
async def test_location_comes_from_the_job_path():
    """Workday collapses multi-site roles to 'N Locations', so locationsText
    is useless; the country lives in externalPath."""
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await Workday().fetch(c, TOKEN, "NVIDIA")
    israeli = [j for j in jobs if j.country == "IL"]
    assert israeli, "fixture should contain Israeli postings"
    assert any("Israel" in j.location for j in israeli)


@respx.mock
async def test_free_text_match_without_israel_in_path_is_not_marked_israeli():
    """searchText='Israel' also matches prose, so the path is the authority."""
    payload = {"total": 1, "jobPostings": [
        {"title": "Engineer", "externalPath": "/job/USA-California/Engineer_JR1",
         "locationsText": "California", "bulletFields": []}]}
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as c:
        jobs = await Workday().fetch(c, TOKEN, "NVIDIA")
    assert jobs[0].country is None


@respx.mock
async def test_hydrate_fills_description():
    respx.post(LIST_URL).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await Workday().fetch(c, TOKEN, "NVIDIA")
        job = jobs[0]
        respx.get(
            f"https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/"
            f"NVIDIAExternalCareerSite{job.job_id}"
        ).mock(return_value=httpx.Response(200, json=DETAIL))
        full = await Workday().hydrate(c, job)
    assert len(full.description) > 50
    assert "<" not in full.description
    assert full.uid == job.uid


async def test_malformed_token_is_rejected_cleanly():
    async with httpx.AsyncClient() as c:
        assert await Workday().fetch(c, "nvidia|wd5", "NVIDIA") == []


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.post(LIST_URL).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        assert await Workday().fetch(c, TOKEN, "NVIDIA") == []
