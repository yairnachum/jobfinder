from __future__ import annotations

import logging
from datetime import datetime

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

log = logging.getLogger(__name__)

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


def _iso(entry: dict) -> str | None:
    postal = (entry.get("address") or {}).get("postalAddress") or {}
    raw = (postal.get("addressCountry") or "").strip().lower()
    if not raw:
        return None
    return _COUNTRY_TO_ISO.get(raw, raw.upper()[:2] if len(raw) == 2 else None)


def _country(item: dict) -> str | None:
    """Country for the posting, preferring Israel across all its offices.

    A multi-office role lists extra offices under `secondaryLocations`. If any
    of them is in Israel the role is open in Israel, so that wins over a
    foreign primary office — missing such a job is worse than including it.
    """
    entries = [item] + list(item.get("secondaryLocations") or [])
    codes = [c for c in (_iso(e) for e in entries) if c]
    if "IL" in codes:
        return "IL"
    return codes[0] if codes else None


def _location(item: dict) -> str:
    """Display location, including secondary offices so the Israel place-name
    fallback can still match when no country code is published."""
    names = [str(item.get("location") or "")]
    for extra in item.get("secondaryLocations") or []:
        name = str(extra.get("location") or "").strip()
        if name:
            names.append(name)
    return ", ".join(n for n in names if n)


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
            if item.get("id") is None:
                log.warning("%s/%s: job with no id, skipping", self.name, token)
                continue
            try:
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
                        location=_location(item),
                        url=item.get("jobUrl") or item.get("applyUrl") or "",
                        description=desc,
                        posted_at=_parse_dt(item.get("publishedAt")),
                        country=_country(item),
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
