"""One malformed record must never cost a whole company's board.

Before this, an unguarded nested .get() raised out of fetch(), was caught only
at board level, and silently dropped every job for that company on every run.
"""
import httpx
import respx

from jobfinder.adapters.ashby import Ashby
from jobfinder.adapters.greenhouse import Greenhouse
from jobfinder.adapters.lever import Lever

GH = "https://boards-api.greenhouse.io/v1/boards/t/jobs?content=true"
ASH = "https://api.ashbyhq.com/posting-api/job-board/t"
LEV = "https://api.lever.co/v0/postings/t?mode=json"


@respx.mock
async def test_greenhouse_skips_malformed_but_keeps_the_rest():
    payload = {"jobs": [
        {"id": 1, "title": "Backend Engineer", "location": "NOT A DICT",
         "absolute_url": "http://x/1", "content": "<p>hi</p>"},
        {"id": 2, "title": "Data Engineer", "location": {"name": "Tel Aviv"},
         "absolute_url": "http://x/2", "content": "<p>hi</p>"},
    ]}
    respx.get(GH).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "t", "T")
    assert [j.job_id for j in jobs] == ["2"]


@respx.mock
async def test_greenhouse_skips_job_with_no_id():
    payload = {"jobs": [
        {"title": "No Id", "location": {"name": "Tel Aviv"}, "content": ""},
        {"id": 7, "title": "Has Id", "location": {"name": "Tel Aviv"}, "content": ""},
    ]}
    respx.get(GH).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "t", "T")
    assert [j.job_id for j in jobs] == ["7"]


@respx.mock
async def test_lever_skips_malformed_but_keeps_the_rest():
    payload = [
        {"id": "a", "text": "Backend", "categories": "NOT A DICT"},
        {"id": "b", "text": "Backend", "categories": {"location": "Tel Aviv"}},
    ]
    respx.get(LEV).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "t", "T")
    assert [j.job_id for j in jobs] == ["b"]


@respx.mock
async def test_ashby_skips_malformed_but_keeps_the_rest():
    payload = {"jobs": [
        {"id": "a", "title": "Backend", "address": "NOT A DICT"},
        {"id": "b", "title": "Backend", "location": "TLV"},
    ]}
    respx.get(ASH).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "t", "T")
    assert [j.job_id for j in jobs] == ["b"]


@respx.mock
async def test_ashby_secondary_location_in_israel_counts():
    """A role whose primary office is abroad but which also lists an Israeli
    office is open in Israel and must not be filtered out."""
    payload = {"jobs": [{
        "id": "a", "title": "Backend Engineer", "location": "New York",
        "address": {"postalAddress": {"addressCountry": "United States"}},
        "secondaryLocations": [
            {"location": "Tel Aviv",
             "address": {"postalAddress": {"addressCountry": "Israel"}}}
        ],
    }]}
    respx.get(ASH).mock(return_value=httpx.Response(200, json=payload))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "t", "T")
    assert jobs[0].country == "IL"
    assert "Tel Aviv" in jobs[0].location
