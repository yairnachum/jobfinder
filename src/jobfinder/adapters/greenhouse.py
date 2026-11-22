from __future__ import annotations

from datetime import datetime

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class Greenhouse:
    name = "greenhouse"
    needs_detail = False

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        data = await fetch_json(client, API.format(token=token))
        if not data or "jobs" not in data:
            return []
        jobs = []
        for item in data["jobs"]:
            jobs.append(
                Job(
                    ats=self.name,
                    token=token,
                    job_id=str(item.get("id")),
                    company=item.get("company_name") or company,
                    title=item.get("title") or "",
                    location=(item.get("location") or {}).get("name", ""),
                    url=item.get("absolute_url") or "",
                    # `content` is entity-escaped HTML; html_to_text handles both passes.
                    description=html_to_text(item.get("content")),
                    posted_at=_parse_dt(
                        item.get("first_published") or item.get("updated_at")
                    ),
                    raw=item,
                )
            )
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        return job
