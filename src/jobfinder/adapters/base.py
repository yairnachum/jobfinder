"""Shared HTTP plumbing and the Adapter protocol."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx

from jobfinder.model import Job

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
TIMEOUT = httpx.Timeout(15.0)


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    method: str = "GET",
    json_body: dict | None = None,
    retries: int = 2,
    backoff: float = 1.0,
) -> Any | None:
    """Fetch JSON, returning None instead of raising.

    One bad board must never abort a whole run, so every failure mode
    collapses to None and is logged.
    """
    # `retries` counts total attempts; 0 would otherwise skip the request
    # entirely and silently return None.
    for attempt in range(max(1, retries)):
        try:
            resp = await client.request(
                method, url, json=json_body,
                headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
            )
            # 404/410 mean the board is gone. Retrying cannot help.
            if resp.status_code in (404, 410):
                log.warning("dead board %s -> %s", url, resp.status_code)
                return None
            # 429 means slow down, not fail. Back off for the server's
            # stated interval rather than burning the remaining attempts.
            if resp.status_code == 429:
                wait = resp.headers.get("Retry-After")
                delay = float(wait) if (wait or "").isdigit() else backoff * 4
                log.warning("rate limited %s, waiting %.1fs", url, delay)
                if attempt + 1 < retries and delay:
                    await asyncio.sleep(min(delay, 20.0))
                continue
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"status {resp.status_code}", request=resp.request, response=resp
                )
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all
            log.warning("fetch failed (%s/%s) %s: %s", attempt + 1, retries, url, exc)
            if attempt + 1 < retries and backoff:
                await asyncio.sleep(backoff * (2 ** attempt))
    return None


class Adapter(Protocol):
    name: str
    # True when descriptions require a second per-job request.
    needs_detail: bool

    async def fetch(
        self, client: httpx.AsyncClient, token: str, company: str
    ) -> list[Job]:
        ...

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        """Fill in the description for adapters where listing omits it."""
        ...
