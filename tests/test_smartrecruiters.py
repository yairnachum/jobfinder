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
async def test_hydrate_swaps_in_the_public_posting_url():
    """The listing gives only an API URL; hydration must replace it with the
    human-facing posting URL, without changing the job's identity.

    Routes are registered most-specific-first: the detail URL is a sub-path of
    the listing URL, and respx resolves overlapping routes in registration
    order, so a leading `url__startswith=BASE` would swallow the detail call.
    """
    job_id = LIST["content"][0]["id"]
    respx.get(f"{BASE}/{job_id}").mock(return_value=httpx.Response(200, json=DETAIL))
    respx.get(url__startswith=f"{BASE}?").mock(
        return_value=httpx.Response(200, json=LIST)
    )
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
        full = await SmartRecruiters().hydrate(c, jobs[0])

    assert full.url == DETAIL["postingUrl"]
    assert full.url != jobs[0].url
    assert "<p>" not in full.description
    assert full.uid == jobs[0].uid, "hydration must not change identity"


@respx.mock
async def test_hydrate_joins_description_sections_as_plain_text():
    """Armis's real detail fixture has a literal '<p>...</p>' placeholder body,
    so a synthetic payload is used to exercise the section joining itself."""
    job_id = LIST["content"][0]["id"]
    detail = {
        "postingUrl": "https://jobs.smartrecruiters.com/Armis/1",
        "jobAd": {
            "sections": {
                "companyDescription": {"text": "<p>We are Armis.</p>"},
                "jobDescription": {"text": "<p>Build the backend services.</p>"},
                "qualifications": {"text": "<ul><li>2+ years of Python</li></ul>"},
                "additionalInformation": {"text": ""},
            }
        },
    }
    respx.get(f"{BASE}/{job_id}").mock(return_value=httpx.Response(200, json=detail))
    respx.get(url__startswith=f"{BASE}?").mock(
        return_value=httpx.Response(200, json=LIST)
    )
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
        full = await SmartRecruiters().hydrate(c, jobs[0])

    assert "Build the backend services." in full.description
    assert "2+ years of Python" in full.description
    # companyDescription is boilerplate marketing, not job requirements.
    assert "We are Armis." not in full.description
    assert "<" not in full.description


@respx.mock
async def test_hydrate_keeps_job_unchanged_when_detail_fetch_fails():
    job_id = LIST["content"][0]["id"]
    respx.get(f"{BASE}/{job_id}").mock(return_value=httpx.Response(500))
    respx.get(url__startswith=f"{BASE}?").mock(
        return_value=httpx.Response(200, json=LIST)
    )
    async with httpx.AsyncClient() as c:
        jobs = await SmartRecruiters().fetch(c, "armis", "Armis")
        full = await SmartRecruiters().hydrate(c, jobs[0])
    assert full == jobs[0]


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
