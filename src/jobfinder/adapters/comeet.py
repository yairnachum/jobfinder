from __future__ import annotations

import logging
from datetime import datetime

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

log = logging.getLogger(__name__)

# Comeet needs two public values: a company uid and a read token, both
# published in the careers page markup. The registry carries them as one
# "uid|token" string so every entry keeps the same shape.
API = ("https://www.comeet.co/careers-api/2.0/company/{uid}/positions"
       "?token={token}&details=true")

# Sections worth reading. The company blurb is marketing, and including it
# would let its boilerplate trip the experience and keyword rules.
_WANTED_SECTIONS = ("description", "requirements", "qualifications")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _description(item: dict) -> str:
    parts = []
    for section in item.get("details") or []:
        if not isinstance(section, dict):
            continue
        name = (section.get("name") or "").strip().lower()
        if name and not any(w in name for w in _WANTED_SECTIONS):
            continue
        parts.append(html_to_text(section.get("value")))
    return " ".join(p for p in parts if p).strip()


class Comeet:
    name = "comeet"
    # details=true returns the sections inline, so no second request.
    needs_detail = False

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        if "|" not in (token or ""):
            log.warning("comeet token must be 'uid|token', got %r", token)
            return []
        uid, read_token = token.split("|", 1)
        data = await fetch_json(client, API.format(uid=uid, token=read_token))
        if not isinstance(data, list):
            return []
        jobs = []
        for item in data:
            if not isinstance(item, dict) or item.get("uid") is None:
                continue
            try:
                loc = item.get("location") or {}
                country = (loc.get("country") or "").strip()
                jobs.append(
                    Job(
                        ats=self.name,
                        token=token,
                        job_id=str(item.get("uid")),
                        company=item.get("company_name") or company,
                        title=item.get("name") or "",
                        location=loc.get("name")
                        or ", ".join(
                            p for p in (loc.get("city"), loc.get("state")) if p
                        ),
                        url=item.get("url_comeet_hosted_page")
                        or item.get("url_active_page") or "",
                        description=_description(item),
                        posted_at=_parse_dt(item.get("time_updated")),
                        country=country.upper() if len(country) == 2 else None,
                        raw=item,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # One malformed record must not cost the whole board.
                log.warning("%s/%s: skipping malformed job: %s",
                            self.name, uid, exc)
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        return job
