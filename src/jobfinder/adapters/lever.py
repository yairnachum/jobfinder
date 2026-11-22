from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

API = "https://api.lever.co/v0/postings/{token}?mode=json"



log = logging.getLogger(__name__)

def _parse_dt(value) -> datetime | None:
    """Lever `createdAt` is epoch MILLISECONDS."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return None


class Lever:
    name = "lever"
    needs_detail = False

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        data = await fetch_json(client, API.format(token=token))
        if not isinstance(data, list):
            return []
        jobs = []
        for item in data:
            cats = item.get("categories") or {}
            country = item.get("country")
            desc = item.get("descriptionPlain") or html_to_text(
                item.get("description")
            )
            if item.get("id") is None:
                log.warning("%s/%s: job with no id, skipping", self.name, token)
                continue
            try:
                jobs.append(
                    Job(
                        ats=self.name,
                        token=token,
                        job_id=str(item.get("id")),
                        company=company,
                        # Lever calls the title `text`.
                        title=item.get("text") or "",
                        location=str(cats.get("location") or ""),
                        url=item.get("hostedUrl") or item.get("applyUrl") or "",
                        description=desc,
                        posted_at=_parse_dt(item.get("createdAt")),
                        country=country.upper()
                        if isinstance(country, str) and len(country) == 2
                        else None,
                        raw=item,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # One malformed record must not cost the whole board.
                log.warning("%s/%s: skipping malformed job: %s",
                            self.name, token, exc)
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        return job
