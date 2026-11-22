from __future__ import annotations

import dataclasses
from datetime import datetime

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

BASE = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE = 100
MAX_PAGES = 20


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _location(loc: dict) -> str:
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    return ", ".join(p for p in parts if p)


class SmartRecruiters:
    name = "smartrecruiters"
    # Listing responses omit descriptions entirely.
    needs_detail = True

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        base = BASE.format(token=token)
        jobs: list[Job] = []
        offset = 0
        for _ in range(MAX_PAGES):
            data = await fetch_json(client, f"{base}?limit={PAGE}&offset={offset}")
            if not data or not data.get("content"):
                break
            for item in data["content"]:
                loc = item.get("location") or {}
                raw_country = (loc.get("country") or "").strip()
                jobs.append(
                    Job(
                        ats=self.name,
                        token=token,
                        job_id=str(item.get("id")),
                        company=(item.get("company") or {}).get("name") or company,
                        title=item.get("name") or "",
                        location=_location(loc),
                        url=f"{base}/{item.get('id')}",
                        description="",  # filled by hydrate()
                        posted_at=_parse_dt(item.get("releasedDate")),
                        # API returns lowercase ISO such as "il".
                        country=raw_country.upper() if len(raw_country) == 2 else None,
                        raw=item,
                    )
                )
            offset += PAGE
            if offset >= data.get("totalFound", 0):
                break
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        base = BASE.format(token=job.token)
        data = await fetch_json(client, f"{base}/{job.job_id}")
        if not data:
            return job
        # Structure is jobAd.sections.{jobDescription,qualifications,...}
        ad = (data.get("jobAd") or {}).get("sections") or {}
        sections = [
            ad.get("jobDescription"),
            ad.get("qualifications"),
            ad.get("additionalInformation"),
        ]
        text = " ".join(
            html_to_text(s.get("text") if isinstance(s, dict) else s)
            for s in sections
            if s
        ).strip()
        return dataclasses.replace(
            job,
            description=text,
            url=data.get("postingUrl") or data.get("applyUrl") or job.url,
        )
