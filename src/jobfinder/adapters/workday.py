from __future__ import annotations

import dataclasses
import logging
import re

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

log = logging.getLogger(__name__)

# Workday identifies a board by tenant, data centre and site, all of which
# appear in the public careers URL. The registry carries them as one
# "tenant|dc|site" string so every entry keeps the same shape.
HOST = "https://{tenant}.{dc}.myworkdayjobs.com"
LIST = HOST + "/wday/cxs/{tenant}/{site}/jobs"
DETAIL = HOST + "/wday/cxs/{tenant}/{site}{path}"
PAGE = 20
MAX_PAGES = 15

# externalPath looks like "/job/Israel-Yokneam/Senior-Engineer_JR123".
_PATH_LOC = re.compile(r"^/job/([^/]+)/")


def _location(posting: dict) -> str:
    """Workday collapses multi-site roles to 'N Locations', so the location
    embedded in the job path is the only per-job signal available."""
    m = _PATH_LOC.match(posting.get("externalPath") or "")
    if m:
        return m.group(1).replace("-", ", ").replace("_", " ")
    return posting.get("locationsText") or ""


class Workday:
    name = "workday"
    # Listings carry no description.
    needs_detail = True

    @staticmethod
    def _parts(token: str):
        bits = (token or "").split("|")
        return bits if len(bits) == 3 else None

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        parts = self._parts(token)
        if not parts:
            log.warning("workday token must be 'tenant|dc|site', got %r", token)
            return []
        tenant, dc, site = parts
        url = LIST.format(tenant=tenant, dc=dc, site=site)
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            data = await fetch_json(
                client, url, method="POST",
                # Searching by country keeps huge global boards tractable;
                # each result is re-checked against the path below.
                json_body={"appliedFacets": {}, "limit": PAGE,
                           "offset": page * PAGE, "searchText": "Israel"},
            )
            if not data or not data.get("jobPostings"):
                break
            for item in data["jobPostings"]:
                path = item.get("externalPath")
                if not path:
                    continue
                try:
                    loc = _location(item)
                    jobs.append(
                        Job(
                            ats=self.name,
                            token=token,
                            job_id=path,
                            company=company,
                            title=item.get("title") or "",
                            location=loc,
                            url=f"{HOST.format(tenant=tenant, dc=dc)}/{site}{path}",
                            description="",  # filled by hydrate()
                            # A free-text search for "Israel" also matches
                            # prose, so only trust the path for the country.
                            country="IL" if "israel" in loc.lower() else None,
                            raw=item,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s/%s: skipping malformed job: %s",
                                self.name, tenant, exc)
            if (page + 1) * PAGE >= data.get("total", 0):
                break
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        parts = self._parts(job.token)
        if not parts:
            return job
        tenant, dc, site = parts
        data = await fetch_json(client, DETAIL.format(
            tenant=tenant, dc=dc, site=site, path=job.job_id))
        if not data:
            return job
        info = data.get("jobPostingInfo") or {}
        return dataclasses.replace(
            job, description=html_to_text(info.get("jobDescription")))
