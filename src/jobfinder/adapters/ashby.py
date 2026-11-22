from __future__ import annotations

from datetime import datetime

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

API = "https://api.ashbyhq.com/posting-api/job-board/{token}"

# Ashby reports a country name, not an ISO code.
_COUNTRY_TO_ISO = {"israel": "IL"}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _country(item: dict) -> str | None:
    postal = (item.get("address") or {}).get("postalAddress") or {}
    raw = (postal.get("addressCountry") or "").strip().lower()
    if not raw:
        return None
    return _COUNTRY_TO_ISO.get(raw, raw.upper()[:2] if len(raw) == 2 else None)


class Ashby:
    name = "ashby"
    needs_detail = False

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        data = await fetch_json(client, API.format(token=token))
        if not data or "jobs" not in data:
            return []
        jobs = []
        for item in data["jobs"]:
            if item.get("isListed") is False:
                continue
            desc = item.get("descriptionPlain") or html_to_text(
                item.get("descriptionHtml")
            )
            jobs.append(
                Job(
                    ats=self.name,
                    token=token,
                    job_id=str(item.get("id")),
                    company=company,
                    title=item.get("title") or "",
                    location=str(item.get("location") or ""),
                    url=item.get("jobUrl") or item.get("applyUrl") or "",
                    description=desc,
                    posted_at=_parse_dt(item.get("publishedAt")),
                    country=_country(item),
                    raw=item,
                )
            )
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        return job
