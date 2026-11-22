import json
import pathlib

import httpx
import respx

from jobfinder.adapters.smartrecruiters import SmartRecruiters

HERE = pathlib.Path(__file__).parent / "fixtures"
LIST = json.loads((HERE / "smartrecruiters_armis.json").read_text())
DETAIL = json.loads((HERE / "smartrecruiters_armis_detail.json").read_text())
BASE = "https://api.smartrecruiters.com/v1/companies/armis/postings"


@respx.mock
async def test_parses_listing():
    respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
    assert len(jobs) == len(LIST["content"])
    assert jobs[0].ats == "smartrecruiters"
    assert jobs[0].title == LIST["content"][0]["name"]


@respx.mock
async def test_country_is_uppercased_from_lowercase_iso():
    """SmartRecruiters returns 'il' lowercase; the model stores 'IL'."""
    respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
    assert any(j.country == "IL" for j in jobs)


@respx.mock
async def test_listing_has_no_description():
    respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
    assert all(j.description == "" for j in jobs)
    assert SmartRecruiters().needs_detail is True


@respx.mock
async def test_hydrate_fills_description_and_url():
    respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json=LIST))
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
        respx.get(f"{BASE}/{jobs[0].job_id}").mock(
            return_value=httpx.Response(200, json=DETAIL)
        )
        full = await SmartRecruiters().hydrate(c, jobs[0])
    assert len(full.description) > 50
    assert "<p>" not in full.description
    assert full.uid == jobs[0].uid, "hydration must not change identity"


@respx.mock
async def test_paginates_when_total_exceeds_page_size():
    page1 = {"offset": 0, "limit": 100, "totalFound": 150,
             "content": LIST["content"][:1] * 100}
    page2 = {"offset": 100, "limit": 100, "totalFound": 150,
             "content": LIST["content"][:1] * 50}
    respx.get(url__startswith=BASE).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
    assert len(jobs) == 150


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get(url__startswith="https://api.smartrecruiters.com/v1/companies/gone").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        assert await SmartRecruiters().fetch(c, "gone", "Gone") == []
