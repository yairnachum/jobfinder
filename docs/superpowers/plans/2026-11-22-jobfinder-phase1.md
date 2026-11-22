# JobFinder Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working pipeline that polls 44 verified Israeli hi-tech ATS job boards every 15 minutes on GitHub Actions and pushes matching junior backend/data roles to Telegram within minutes of publication.

**Architecture:** Async HTTP fan-out over a YAML registry of `company → ATS + board token`. Four ATS adapters normalize wildly different payloads into one `Job` record. A two-stage deterministic filter (title/location first, then description) decides relevance. Seen-state persists to a dedicated `state` git branch because GitHub Actions is stateless.

**Tech Stack:** Python 3.12, `httpx` (async), `PyYAML`, `pytest`, `uv` for dependency management, GitHub Actions for scheduling.

---

## Background: Verified Research

All of the following was confirmed live against the real APIs on 2026-11-22. Do not
re-derive it; it is correct.

### Exact payload field names

| ATS | Title | Location | Country | URL | Description | Published |
|---|---|---|---|---|---|---|
| Greenhouse | `title` | `location.name` | — | `absolute_url` | `content` (HTML-**escaped**) | `first_published` |
| Ashby | `title` | `location` | `address.postalAddress.addressCountry` | `jobUrl` | `descriptionPlain` | `publishedAt` |
| Lever | `text` | `categories.location` | `country` (ISO-2) | `hostedUrl` | `descriptionPlain` | `createdAt` (epoch **ms**) |
| SmartRecruiters | `name` | `location.city` / `.region` | `location.country` (ISO-2, **lowercase**) | `ref`→detail `postingUrl` | detail only | `releasedDate` |

Critical details that will cause bugs if missed:

- **Greenhouse `content` is HTML-entity-escaped HTML.** It must be `html.unescape()`d
  *before* tag stripping, or the output is full of `&lt;p&gt;`.
- **Lever `createdAt` is epoch milliseconds**, not seconds. Dividing wrong puts every job
  in 1970 or the year 58000.
- **SmartRecruiters country is lowercase** (`"il"`). Compare case-insensitively.
- **SmartRecruiters list responses contain no description.** It requires a second call to
  `/v1/companies/{token}/postings/{id}`, whose `jobAd` has keys `companyDescription`,
  `jobDescription`, `qualifications`, `additionalInformation`. This is why the filter is
  two-stage — see Task 13.
- **Ashby location is often an abbreviation** like `"TLV"`, so the `addressCountry` field
  is the reliable signal.
- **Ashby tokens are case-sensitive** (`Snyk`, not `snyk`, for some boards).
- SmartRecruiters paginates with `limit` (max 100) and `offset`; `totalFound` gives the total.

### Why name-verification is mandatory

Slug-probing produces confident false positives. All of these resolved to the **wrong
company** and must never enter the registry:

| Guessed slug | Actually is |
|---|---|
| `vast` | "Vast" — a California space company, not VAST Data |
| `trigo` | "TRIGO" — a French quality-services firm, not Trigo Vision |
| `vega` | "Vega Academy", Toronto |
| `riseup` | "Rise Up", Paris |
| `gong` (SmartRecruiters) | "GONG!" of New York — the real Gong.io is `gongio` on Greenhouse |
| `quantum` (Ashby) | a London company, not Quantum Machines |

### Why "has Israeli jobs" is a verification signal but NOT a registry filter

Snyk, Pagaya, Descope, Bringg, Hibob and Fiverr all have valid, correctly-identified
boards with **zero Israeli openings right now**. They belong in the registry — a company
with no opening today is exactly who you want to be watching for tomorrow. Dropping them
defeats the purpose of the project. They are included below with `il_verified: false`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Deps, pytest config |
| `src/jobfinder/model.py` | `Job` dataclass, stable `uid` |
| `src/jobfinder/textutil.py` | HTML → plain text |
| `src/jobfinder/adapters/base.py` | `Adapter` protocol, retrying HTTP helper |
| `src/jobfinder/adapters/greenhouse.py` | Greenhouse normalizer |
| `src/jobfinder/adapters/ashby.py` | Ashby normalizer |
| `src/jobfinder/adapters/lever.py` | Lever normalizer |
| `src/jobfinder/adapters/smartrecruiters.py` | SmartRecruiters normalizer + detail hydration |
| `src/jobfinder/adapters/__init__.py` | `ADAPTERS` dispatch table |
| `src/jobfinder/filter.py` | Location, seniority, experience, role-family rules |
| `src/jobfinder/store.py` | `seen.jsonl`, dedupe, retry queue, pruning |
| `src/jobfinder/notify.py` | Telegram formatting + send |
| `src/jobfinder/config.py` | Profile/registry loading |
| `src/jobfinder/watch.py` | Orchestration, `--seed` mode |
| `registry/companies.yaml` | 44 verified seed boards |
| `config/profile.yaml` | Keywords, thresholds |
| `.github/workflows/watch.yml` | 15-minute cron |
| `tests/fixtures/*.json` | Recorded real payloads |

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `src/jobfinder/__init__.py`, `tests/__init__.py`, `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "jobfinder"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "respx>=0.21"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jobfinder"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create package markers**

```bash
mkdir -p src/jobfinder/adapters tests/fixtures registry config .github/workflows
touch src/jobfinder/__init__.py src/jobfinder/adapters/__init__.py tests/__init__.py
```

- [ ] **Step 3: Install and verify**

Run: `uv venv --python 3.12 && uv pip install -e ".[dev]"`
Expected: installs without error.

Run: `uv run pytest --version`
Expected: prints a pytest 8.x version banner.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src tests .gitignore
git commit -m "chore: scaffold jobfinder package"
```

---

## Task 2: The `Job` model

**Files:**
- Create: `src/jobfinder/model.py`
- Test: `tests/test_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model.py
from datetime import datetime, timezone
from jobfinder.model import Job


def _job(**kw):
    base = dict(
        ats="greenhouse", token="jfrog", job_id="123",
        company="JFrog", title="Backend Engineer",
        location="Tel Aviv, Israel", url="https://example.com/1",
        description="We are hiring.",
    )
    base.update(kw)
    return Job(**base)


def test_uid_is_stable_across_instances():
    assert _job().uid == _job().uid


def test_uid_changes_with_job_id():
    assert _job(job_id="123").uid != _job(job_id="124").uid


def test_uid_ignores_title_edits():
    """Employers edit titles; that must not resurface a job as new."""
    assert _job(title="Backend Engineer").uid == _job(title="Backend Engineer II").uid


def test_uid_distinguishes_same_job_id_on_different_boards():
    a = _job(ats="greenhouse", token="a", job_id="1")
    b = _job(ats="lever", token="a", job_id="1")
    assert a.uid != b.uid


def test_country_defaults_to_none():
    assert _job().country is None


def test_posted_at_is_optional():
    j = _job(posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert j.posted_at.year == 2026
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.model'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/model.py
"""The normalized job record every adapter produces."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Job:
    ats: str
    token: str
    job_id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    posted_at: datetime | None = None
    # ISO-3166 alpha-2, uppercased, only when the ATS supplies it.
    country: str | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def uid(self) -> str:
        """Stable primary key.

        Derived from the ATS-assigned job id, never from mutable fields like
        the title, so an employer editing a posting does not resurface it.
        """
        return hashlib.sha1(
            f"{self.ats}:{self.token}:{self.job_id}".encode()
        ).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/model.py tests/test_model.py
git commit -m "feat: add normalized Job model with stable uid"
```

---

## Task 3: HTML to plain text

**Files:**
- Create: `src/jobfinder/textutil.py`
- Test: `tests/test_textutil.py`

Greenhouse returns entity-escaped HTML; the filter needs readable text to find
experience requirements.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_textutil.py
from jobfinder.textutil import html_to_text


def test_strips_tags():
    assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_unescapes_entities_then_strips():
    """Greenhouse double-encodes: entities must be decoded before stripping."""
    assert html_to_text("&lt;p&gt;3+ years&lt;/p&gt;") == "3+ years"


def test_collapses_whitespace():
    assert html_to_text("<p>a</p>\n\n\n<p>b</p>") == "a b"


def test_list_items_separated():
    out = html_to_text("<ul><li>Python</li><li>Go</li></ul>")
    assert "Python" in out and "Go" in out
    assert "PythonGo" not in out


def test_handles_empty_and_none():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_preserves_hebrew():
    assert "שנות ניסיון" in html_to_text("<p>3 שנות ניסיון</p>")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_textutil.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.textutil'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/textutil.py
"""HTML normalization shared by the adapters."""
from __future__ import annotations

import html
import re

_BLOCK = re.compile(r"</(p|div|li|tr|h[1-6]|ul|ol|br)\s*>|<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(raw: str | None) -> str:
    """Convert (possibly entity-escaped) HTML into collapsed plain text."""
    if not raw:
        return ""
    # Greenhouse ships entity-escaped markup, so decode before stripping.
    text = html.unescape(raw)
    # Keep block boundaries from fusing words together.
    text = _BLOCK.sub(" ", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_textutil.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/textutil.py tests/test_textutil.py
git commit -m "feat: add HTML to plain text conversion"
```

---

## Task 4: Adapter base and retrying fetch

**Files:**
- Create: `src/jobfinder/adapters/base.py`
- Test: `tests/test_adapter_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adapter_base.py
import httpx
import pytest
import respx

from jobfinder.adapters.base import fetch_json


@respx.mock
async def test_returns_parsed_json():
    respx.get("https://x.test/j").mock(return_value=httpx.Response(200, json={"ok": 1}))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j") == {"ok": 1}


@respx.mock
async def test_retries_then_succeeds():
    route = respx.get("https://x.test/j").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": 2})]
    )
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=2, backoff=0) == {"ok": 2}
    assert route.call_count == 2


@respx.mock
async def test_returns_none_on_404_without_retrying():
    """A 404 is a dead board, not a transient fault — retrying wastes the run."""
    route = respx.get("https://x.test/j").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=3, backoff=0) is None
    assert route.call_count == 1


@respx.mock
async def test_returns_none_after_exhausting_retries():
    respx.get("https://x.test/j").mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=2, backoff=0) is None


@respx.mock
async def test_returns_none_on_malformed_json():
    respx.get("https://x.test/j").mock(return_value=httpx.Response(200, text="not json"))
    async with httpx.AsyncClient() as c:
        assert await fetch_json(c, "https://x.test/j", retries=1, backoff=0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adapter_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.adapters.base'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/adapters/base.py
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
    for attempt in range(retries):
        try:
            resp = await client.request(
                method, url, json=json_body,
                headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
            )
            # 404/410 mean the board is gone. Retrying cannot help.
            if resp.status_code in (404, 410):
                log.warning("dead board %s -> %s", url, resp.status_code)
                return None
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adapter_base.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/adapters/base.py tests/test_adapter_base.py
git commit -m "feat: add adapter protocol and resilient JSON fetch"
```

---

## Task 5: Record real API fixtures

**Files:**
- Create: `tests/fixtures/greenhouse_jfrog.json`, `tests/fixtures/ashby_lemonade.json`,
  `tests/fixtures/lever_walkme.json`, `tests/fixtures/smartrecruiters_armis.json`,
  `tests/fixtures/smartrecruiters_armis_detail.json`
- Create: `scripts/record_fixtures.py`

Tests must run offline and deterministically, so real payloads are recorded once.

- [ ] **Step 1: Write the recorder script**

```python
# scripts/record_fixtures.py
"""Re-record ATS fixtures. Run manually; not part of the test suite."""
import json
import pathlib
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 Chrome/131.0"}
OUT = pathlib.Path(__file__).parent.parent / "tests" / "fixtures"

TARGETS = {
    "greenhouse_jfrog.json":
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true",
    "ashby_lemonade.json":
        "https://api.ashbyhq.com/posting-api/job-board/lemonade",
    "lever_walkme.json":
        "https://api.lever.co/v0/postings/walkme?mode=json",
    "smartrecruiters_armis.json":
        "https://api.smartrecruiters.com/v1/companies/armis/postings?limit=100",
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in TARGETS.items():
        data = get(url)
        (OUT / name).write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print(f"wrote {name}")

    # SmartRecruiters descriptions need a second call; record one detail payload.
    listing = json.loads((OUT / "smartrecruiters_armis.json").read_text())
    job_id = listing["content"][0]["id"]
    detail = get(
        f"https://api.smartrecruiters.com/v1/companies/armis/postings/{job_id}"
    )
    (OUT / "smartrecruiters_armis_detail.json").write_text(
        json.dumps(detail, indent=1, ensure_ascii=False)
    )
    print("wrote smartrecruiters_armis_detail.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `uv run python scripts/record_fixtures.py`
Expected: five `wrote ...` lines.

- [ ] **Step 3: Verify the fixtures are non-trivial**

Run: `wc -c tests/fixtures/*.json`
Expected: each file is more than 1000 bytes.

- [ ] **Step 4: Commit**

```bash
git add scripts/record_fixtures.py tests/fixtures
git commit -m "test: record real ATS payload fixtures"
```

---

## Task 6: Greenhouse adapter

**Files:**
- Create: `src/jobfinder/adapters/greenhouse.py`
- Test: `tests/test_greenhouse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_greenhouse.py
import json
import pathlib

import httpx
import respx

from jobfinder.adapters.greenhouse import Greenhouse

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "greenhouse_jfrog.json").read_text()
)


@respx.mock
async def test_parses_real_payload():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "jfrog", "JFrog")

    assert len(jobs) == len(FIX["jobs"])
    j = jobs[0]
    assert j.ats == "greenhouse"
    assert j.company == "JFrog"
    assert j.title
    assert j.url.startswith("http")
    assert j.job_id


@respx.mock
async def test_description_is_unescaped_plain_text():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "jfrog", "JFrog")
    body = " ".join(j.description for j in jobs)
    assert "&lt;" not in body
    assert "<p>" not in body


@respx.mock
async def test_finds_israeli_locations():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/jfrog/jobs?content=true"
    ).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Greenhouse().fetch(c, "jfrog", "JFrog")
    assert any("israel" in j.location.lower() for j in jobs)


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get(
        "https://boards-api.greenhouse.io/v1/boards/gone/jobs?content=true"
    ).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        assert await Greenhouse().fetch(c, "gone", "Gone") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_greenhouse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.adapters.greenhouse'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/adapters/greenhouse.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_greenhouse.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/adapters/greenhouse.py tests/test_greenhouse.py
git commit -m "feat: add Greenhouse adapter"
```

---

## Task 7: Ashby adapter

**Files:**
- Create: `src/jobfinder/adapters/ashby.py`
- Test: `tests/test_ashby.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ashby.py
import json
import pathlib

import httpx
import respx

from jobfinder.adapters.ashby import Ashby

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "ashby_lemonade.json").read_text()
)
URL = "https://api.ashbyhq.com/posting-api/job-board/lemonade"


@respx.mock
async def test_parses_real_payload():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "lemonade", "Lemonade")
    assert len(jobs) == len(FIX["jobs"])
    assert jobs[0].ats == "ashby"
    assert jobs[0].company == "Lemonade"


@respx.mock
async def test_extracts_country_from_postal_address():
    """Ashby location is often an abbreviation like 'TLV';
    addressCountry is the reliable signal."""
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "lemonade", "Lemonade")
    assert any(j.country == "IL" for j in jobs)


@respx.mock
async def test_uses_plain_description():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Ashby().fetch(c, "lemonade", "Lemonade")
    assert any(j.description for j in jobs)
    assert all("<p>" not in j.description for j in jobs)


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/gone").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        assert await Ashby().fetch(c, "gone", "Gone") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ashby.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.adapters.ashby'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/adapters/ashby.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ashby.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/adapters/ashby.py tests/test_ashby.py
git commit -m "feat: add Ashby adapter"
```

---

## Task 8: Lever adapter

**Files:**
- Create: `src/jobfinder/adapters/lever.py`
- Test: `tests/test_lever.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lever.py
import json
import pathlib

import httpx
import respx

from jobfinder.adapters.lever import Lever

FIX = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "lever_walkme.json").read_text()
)
URL = "https://api.lever.co/v0/postings/walkme?mode=json"


@respx.mock
async def test_parses_real_payload():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "walkme", "WalkMe")
    assert len(jobs) == len(FIX)
    assert jobs[0].ats == "lever"


def test_title_comes_from_text_field():
    assert "text" in FIX[0], "Lever stores the title in `text`, not `title`"


@respx.mock
async def test_created_at_is_milliseconds_not_seconds():
    """Lever createdAt is epoch ms. Treating it as seconds lands in the far future."""
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "walkme", "WalkMe")
    dated = [j for j in jobs if j.posted_at]
    assert dated, "fixture should contain at least one dated posting"
    for j in dated:
        assert 2000 <= j.posted_at.year <= 2100, f"bad year {j.posted_at}"
        assert j.posted_at.tzinfo is not None


@respx.mock
async def test_country_is_uppercased_iso():
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIX))
    async with httpx.AsyncClient() as c:
        jobs = await Lever().fetch(c, "walkme", "WalkMe")
    for j in jobs:
        if j.country:
            assert j.country.isupper() and len(j.country) == 2


@respx.mock
async def test_dead_board_returns_empty_list():
    respx.get("https://api.lever.co/v0/postings/gone?mode=json").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as c:
        assert await Lever().fetch(c, "gone", "Gone") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lever.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.adapters.lever'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/adapters/lever.py
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from jobfinder.adapters.base import fetch_json
from jobfinder.model import Job
from jobfinder.textutil import html_to_text

API = "https://api.lever.co/v0/postings/{token}?mode=json"


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
                    country=country.upper() if isinstance(country, str) and len(country) == 2 else None,
                    raw=item,
                )
            )
        return jobs

    async def hydrate(self, client: httpx.AsyncClient, job: Job) -> Job:
        return job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lever.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/adapters/lever.py tests/test_lever.py
git commit -m "feat: add Lever adapter"
```

---

## Task 9: SmartRecruiters adapter with pagination and detail hydration

**Files:**
- Create: `src/jobfinder/adapters/smartrecruiters.py`
- Test: `tests/test_smartrecruiters.py`

This is the only adapter where descriptions cost an extra request per job, which is why
`needs_detail` exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smartrecruiters.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_smartrecruiters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.adapters.smartrecruiters'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/adapters/smartrecruiters.py
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
            for s in sections if s
        ).strip()
        return dataclasses.replace(
            job,
            description=text,
            url=data.get("postingUrl") or data.get("applyUrl") or job.url,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_smartrecruiters.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/adapters/smartrecruiters.py tests/test_smartrecruiters.py
git commit -m "feat: add SmartRecruiters adapter with pagination and detail hydration"
```

---

## Task 10: Adapter dispatch table

**Files:**
- Modify: `src/jobfinder/adapters/__init__.py`
- Test: `tests/test_adapter_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adapter_registry.py
import pytest

from jobfinder.adapters import ADAPTERS, get_adapter


def test_all_four_adapters_registered():
    assert set(ADAPTERS) == {"greenhouse", "ashby", "lever", "smartrecruiters"}


@pytest.mark.parametrize("name", ["greenhouse", "ashby", "lever", "smartrecruiters"])
def test_adapter_name_matches_key(name):
    assert get_adapter(name).name == name


def test_only_smartrecruiters_needs_detail():
    assert get_adapter("smartrecruiters").needs_detail is True
    for name in ("greenhouse", "ashby", "lever"):
        assert get_adapter(name).needs_detail is False


def test_unknown_adapter_raises():
    with pytest.raises(KeyError):
        get_adapter("workday")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adapter_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'ADAPTERS'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/adapters/__init__.py
"""Adapter dispatch. Adding an ATS means adding one module and one entry here."""
from __future__ import annotations

from jobfinder.adapters.ashby import Ashby
from jobfinder.adapters.base import Adapter
from jobfinder.adapters.greenhouse import Greenhouse
from jobfinder.adapters.lever import Lever
from jobfinder.adapters.smartrecruiters import SmartRecruiters

ADAPTERS: dict[str, Adapter] = {
    a.name: a for a in (Greenhouse(), Ashby(), Lever(), SmartRecruiters())
}


def get_adapter(name: str) -> Adapter:
    return ADAPTERS[name]


__all__ = ["ADAPTERS", "get_adapter", "Adapter"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adapter_registry.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/adapters/__init__.py tests/test_adapter_registry.py
git commit -m "feat: add adapter dispatch table"
```

---

## Task 11: Location filter

**Files:**
- Create: `src/jobfinder/filter.py`
- Test: `tests/test_filter_location.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filter_location.py
import pytest

from jobfinder.filter import is_israel
from jobfinder.model import Job


def mk(location="", country=None):
    return Job(ats="x", token="t", job_id="1", company="C", title="T",
               location=location, url="u", description="", country=country)


@pytest.mark.parametrize("loc", [
    "Tel Aviv, Israel", "Tel Aviv-Yafo", "TLV", "Herzliya",
    "Israel - Raanana", "Ra'anana", "Haifa", "Jerusalem", "Be'er Sheva",
    "Netanya", "Petah Tikva", "Ramat Gan", "Yokneam", "Rehovot",
    "Airport City", "Tel Aviv District, Israel", "ישראל", "תל אביב",
])
def test_israeli_locations_match(loc):
    assert is_israel(mk(location=loc)) is True


@pytest.mark.parametrize("loc", [
    "London, England, United Kingdom", "New York, NY", "Paris, fr",
    "Toronto, ON", "Remote - US", "Bangalore", "Hawthorne, California",
])
def test_foreign_locations_do_not_match(loc):
    assert is_israel(mk(location=loc)) is False


def test_country_code_wins_over_blank_location():
    assert is_israel(mk(location="", country="IL")) is True


def test_country_code_rejects_when_explicitly_foreign():
    """An explicit foreign ISO code beats a misleading city string."""
    assert is_israel(mk(location="Tel Aviv Street, London", country="GB")) is False


def test_empty_location_without_country_is_not_israel():
    assert is_israel(mk()) is False


def test_substring_false_positive_guarded():
    """'Israelite Road' style strings should not pass on a bare substring."""
    assert is_israel(mk(location="Mount Israel, Ohio")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filter_location.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.filter'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/filter.py
"""Deterministic relevance rules. No network, no model calls."""
from __future__ import annotations

import re

from jobfinder.model import Job

# Cities and regions, matched on word boundaries.
_IL_PLACES = [
    r"israel", r"ישראל", r"תל[\s-]?אביב",
    r"tel[\s-]?aviv(?:-yafo)?", r"tlv", r"herzl[iy]+a", r"ra['’]?anana",
    r"haifa", r"jerusalem", r"be['’]?er[\s-]?sheva", r"beer[\s-]?sheva",
    r"netanya", r"petah[\s-]?tikva", r"ramat[\s-]?gan", r"rehovot",
    r"yokneam", r"caesarea", r"kfar[\s-]?saba", r"hod[\s-]?hasharon",
    r"airport[\s-]?city", r"modi['’]?in", r"migdal[\s-]?ha['’]?emek",
    r"ashdod", r"rishon[\s-]?lezion", r"givatayim", r"or[\s-]?yehuda",
    r"holon", r"lod", r"nes[\s-]?ziona", r"bnei[\s-]?brak", r"ashkelon",
]
_IL_RE = re.compile(r"(?<![a-z])(" + "|".join(_IL_PLACES) + r")(?![a-z])", re.I)

# "Mount Israel, Ohio" and similar: an Israel token next to a foreign marker.
_FOREIGN_RE = re.compile(
    r"\b(ohio|united states|usa|u\.s\.|canada|ontario|california|texas|"
    r"new york|london|england|uk|united kingdom|germany|france|india|"
    r"poland|romania|ukraine|australia|singapore|japan|brazil|mexico)\b",
    re.I,
)


def is_israel(job: Job) -> bool:
    """True when the posting is located in Israel.

    An explicit ISO country code from the ATS is authoritative; otherwise fall
    back to matching place names in the display string.
    """
    if job.country:
        return job.country.upper() == "IL"
    text = job.location or ""
    if not _IL_RE.search(text):
        return False
    # Guard against a place name colliding with a foreign location.
    if _FOREIGN_RE.search(text):
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_filter_location.py -v`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/filter.py tests/test_filter_location.py
git commit -m "feat: add Israel location filter"
```

---

## Task 12: Seniority and role-family filters

**Files:**
- Modify: `src/jobfinder/filter.py`
- Test: `tests/test_filter_title.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filter_title.py
import pytest

from jobfinder.filter import role_family, seniority_ok


@pytest.mark.parametrize("title", [
    "Senior Backend Engineer", "Sr. Software Engineer", "Staff Engineer",
    "Principal Data Scientist", "Backend Team Lead", "Engineering Manager",
    "Head of Data", "Director of Product Engineering", "VP R&D",
    "Software Architect", "Group Lead, Platform", "Chief Technology Officer",
    "Data Engineering Tech Lead",
])
def test_senior_titles_rejected(title):
    assert seniority_ok(title) is False


@pytest.mark.parametrize("title", [
    "Backend Engineer", "Junior Software Engineer", "Software Engineer",
    "Data Analyst", "Entry Level Developer", "Graduate Software Engineer",
    "Student - Backend", "Associate Data Scientist", "Full Stack Developer",
])
def test_junior_and_neutral_titles_accepted(title):
    assert seniority_ok(title) is True


def test_leadership_word_inside_other_word_not_matched():
    """'Leader' must match, but 'Pipeline' must not trip the 'lead' rule."""
    assert seniority_ok("Data Pipeline Engineer") is True


@pytest.mark.parametrize("title,family", [
    ("Backend Engineer", "backend"),
    ("Full Stack Developer", "backend"),
    ("Software Engineer", "backend"),
    ("Python Developer", "backend"),
    ("Data Engineer", "data"),
    ("Data Analyst", "data"),
    ("Machine Learning Engineer", "data"),
    ("AI Engineer", "data"),
    ("Algorithm Engineer", "data"),
    ("NLP Researcher", "data"),
])
def test_role_families_detected(title, family):
    assert role_family(title) == family


@pytest.mark.parametrize("title", [
    "Account Executive", "Sales Development Representative",
    "Marketing Manager", "Recruiter", "Office Manager",
    "Customer Success Manager", "Assistant Controller, Revenues",
    "Compensation & Benefits Manager", "Product Designer",
])
def test_non_engineering_titles_have_no_family(title):
    assert role_family(title) is None


def test_qa_is_not_in_scope_for_phase_one():
    """User selected backend and data only."""
    assert role_family("QA Automation Engineer") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filter_title.py -v`
Expected: FAIL — `ImportError: cannot import name 'seniority_ok'`

- [ ] **Step 3: Append the implementation to `src/jobfinder/filter.py`**

```python
# --- appended to src/jobfinder/filter.py ---

_SENIOR_RE = re.compile(
    r"\b("
    r"senior|sr\.?|staff|principal|lead|leader|head|director|vp|"
    r"vice\s+president|chief|manager|architect|expert|distinguished|fellow"
    r")\b",
    re.I,
)

_EXCLUDE_FUNCTION_RE = re.compile(
    r"\b("
    r"sales|marketing|recruit\w*|talent|hr\b|human\s+resources|finance|"
    r"controller|legal|counsel|customer\s+success|account\s+executive|"
    r"bdr|sdr|office\s+manager|designer|design|content|copywriter|"
    r"compensation|benefits|procurement|facilities|executive\s+assistant"
    r")\b",
    re.I,
)

_BACKEND_RE = re.compile(
    r"\b("
    r"backend|back[\s-]end|full[\s-]?stack|fullstack|software\s+engineer|"
    r"software\s+developer|swe\b|server[\s-]side|platform\s+engineer|"
    r"python|java\b|node(?:\.js)?|golang|\bgo\b|c#|\.net|ruby|scala|kotlin|"
    r"infrastructure\s+engineer|developer"
    r")\b",
    re.I,
)

_DATA_RE = re.compile(
    r"\b("
    r"data\s+engineer|data\s+analyst|data\s+scientist|big\s+data|"
    r"machine\s+learning|\bml\b|ai\s+engineer|\bai\b|deep\s+learning|"
    r"nlp\b|computer\s+vision|algorithm|research\s+engineer|analytics|"
    r"bi\s+developer|mlops"
    r")\b",
    re.I,
)


def seniority_ok(title: str) -> bool:
    """False when the title is explicitly senior or a leadership role."""
    return not _SENIOR_RE.search(title or "")


def role_family(title: str) -> str | None:
    """Return 'backend', 'data', or None when out of scope."""
    t = title or ""
    if _EXCLUDE_FUNCTION_RE.search(t):
        return None
    # Data is checked first: "Data Engineer" also matches the backend
    # "engineer" pattern, and the more specific family should win.
    if _DATA_RE.search(t):
        return "data"
    if _BACKEND_RE.search(t):
        return "backend"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_filter_title.py -v`
Expected: 43 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/filter.py tests/test_filter_title.py
git commit -m "feat: add seniority and role-family filters"
```

---

## Task 13: Experience-years extraction and the two-stage filter

**Files:**
- Modify: `src/jobfinder/filter.py`
- Test: `tests/test_filter_experience.py`

The filter is deliberately split. `passes_stage_one` needs only title and location, so
SmartRecruiters jobs can be rejected before paying for a detail request.
`passes_stage_two` needs the description.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filter_experience.py
import pytest

from jobfinder.filter import min_years, passes_stage_one, passes_stage_two
from jobfinder.model import Job


def mk(title="Backend Engineer", location="Tel Aviv, Israel",
       description="", country=None):
    return Job(ats="x", token="t", job_id="1", company="C", title=title,
               location=location, url="u", description=description,
               country=country)


@pytest.mark.parametrize("text,expected", [
    ("5+ years of experience", 5),
    ("3-5 years of experience", 3),
    ("at least 4 years experience", 4),
    ("minimum of 2 years", 2),
    ("2+ yrs experience", 2),
    ("1 year of experience", 1),
    ("7 years' experience in backend", 7),
    ("3 שנות ניסיון", 3),
    ("לפחות 5 שנות ניסיון", 5),
])
def test_extracts_minimum_years(text, expected):
    assert min_years(text) == expected


def test_returns_none_when_no_requirement_stated():
    assert min_years("We are looking for a great engineer.") is None


def test_picks_the_lowest_requirement_when_several_appear():
    """Descriptions list several stacks; the lowest bar is the real entry bar."""
    assert min_years("5+ years in Java. 2+ years with Python.") == 2


def test_ignores_unrelated_numbers():
    assert min_years("We are a team of 200 people founded 10 years ago") is None


# --- stage one: title + location only ---

def test_stage_one_accepts_junior_israeli_backend():
    assert passes_stage_one(mk()) is True


def test_stage_one_rejects_foreign():
    assert passes_stage_one(mk(location="London, UK")) is False


def test_stage_one_rejects_senior():
    assert passes_stage_one(mk(title="Senior Backend Engineer")) is False


def test_stage_one_rejects_out_of_family():
    assert passes_stage_one(mk(title="Account Executive")) is False


# --- stage two: description ---

def test_stage_two_accepts_zero_to_three_years():
    assert passes_stage_two(mk(description="2+ years of experience")) is True


def test_stage_two_rejects_four_plus_years():
    assert passes_stage_two(mk(description="4+ years of experience")) is False


def test_stage_two_accepts_when_experience_unstated():
    """Moderate setting: silence is not a rejection."""
    assert passes_stage_two(mk(description="Join our team!")) is True


def test_stage_two_accepts_empty_description():
    assert passes_stage_two(mk(description="")) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filter_experience.py -v`
Expected: FAIL — `ImportError: cannot import name 'min_years'`

- [ ] **Step 3: Append the implementation to `src/jobfinder/filter.py`**

```python
# --- appended to src/jobfinder/filter.py ---

MAX_YEARS = 3  # "moderate" setting: 4+ years is out of scope.

_UNITS = r"(?:years?|yrs?|שנות|שנים)"

# "5 years of experience", "3 שנות ניסיון" — a span followed by an
# experience word. The gap is bounded so it cannot leap across a sentence.
_RE_YEARS_EXP = re.compile(
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*" + _UNITS +
    r"[^.\n]{0,24}?(?:experience|exp\b|ניסיון)",
    re.I,
)
# "minimum of 2 years", "at least 4 years" — a qualifier makes it a
# requirement even with no "experience" word.
_RE_QUALIFIED = re.compile(
    r"(?:at\s+least|minimum\s+of|minimum|min\.|over|more\s+than|לפחות)\s*"
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*" + _UNITS,
    re.I,
)
# "2+ years" — an explicit plus is a requirement on its own. This is what
# distinguishes "2+ years with Python" from "founded 10 years ago".
_RE_PLUS = re.compile(r"(\d{1,2})\s*\+\s*" + _UNITS, re.I)

_YEARS_PATTERNS = (_RE_YEARS_EXP, _RE_QUALIFIED, _RE_PLUS)


def min_years(description: str) -> int | None:
    """Lowest stated years-of-experience requirement, or None.

    Descriptions often list several stacks with different bars; the lowest is
    the real entry requirement. A bare "N years" with neither a qualifier nor
    an experience word is ignored, so prose like "founded 10 years ago" does
    not read as a requirement.
    """
    if not description:
        return None
    found = [
        int(m.group(1))
        for pattern in _YEARS_PATTERNS
        for m in pattern.finditer(description)
    ]
    found = [n for n in found if 0 <= n <= 20]
    return min(found) if found else None


def passes_stage_one(job: Job) -> bool:
    """Title and location only — cheap, runs before any detail fetch."""
    return (
        is_israel(job)
        and seniority_ok(job.title)
        and role_family(job.title) is not None
    )


def passes_stage_two(job: Job) -> bool:
    """Description-based checks. Requires a hydrated job."""
    years = min_years(job.description)
    return years is None or years <= MAX_YEARS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_filter_experience.py -v`
Expected: 20 passed

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass, no failures.

- [ ] **Step 6: Commit**

```bash
git add src/jobfinder/filter.py tests/test_filter_experience.py
git commit -m "feat: add experience extraction and two-stage filter"
```

---

## Task 14: Seen-state store

**Files:**
- Create: `src/jobfinder/store.py`
- Test: `tests/test_store.py`

A job must never be recorded as seen if its notification failed, or it is lost forever.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
import time

from jobfinder.store import SeenStore


def test_new_store_treats_everything_as_unseen(tmp_path):
    s = SeenStore(tmp_path / "seen.jsonl")
    assert s.is_new("abc") is True


def test_marked_jobs_are_not_new(tmp_path):
    s = SeenStore(tmp_path / "seen.jsonl")
    s.mark("abc", company="C", title="T")
    assert s.is_new("abc") is False


def test_state_survives_reload(tmp_path):
    p = tmp_path / "seen.jsonl"
    s = SeenStore(p)
    s.mark("abc", company="C", title="T")
    s.save()
    assert SeenStore(p).is_new("abc") is False


def test_marking_twice_does_not_duplicate_records(tmp_path):
    p = tmp_path / "seen.jsonl"
    s = SeenStore(p)
    s.mark("abc", company="C", title="T")
    s.mark("abc", company="C", title="T")
    s.save()
    assert len(p.read_text().strip().splitlines()) == 1


def test_prune_drops_old_entries(tmp_path):
    p = tmp_path / "seen.jsonl"
    s = SeenStore(p)
    old = time.time() - 200 * 86400
    s.mark("old", company="C", title="T", first_seen=old)
    s.mark("new", company="C", title="T")
    s.prune(max_age_days=120)
    s.save()
    reloaded = SeenStore(p)
    assert reloaded.is_new("old") is True
    assert reloaded.is_new("new") is False


def test_seed_marks_without_notifying(tmp_path):
    """Cold start: record everything, notify nothing."""
    s = SeenStore(tmp_path / "seen.jsonl")
    s.seed(["a", "b", "c"])
    assert all(not s.is_new(u) for u in "abc")


def test_pending_queue_round_trips(tmp_path):
    p = tmp_path / "seen.jsonl"
    s = SeenStore(p)
    s.add_pending("failed-uid")
    s.save()
    assert "failed-uid" in SeenStore(p).pending()


def test_clearing_pending_removes_it(tmp_path):
    p = tmp_path / "seen.jsonl"
    s = SeenStore(p)
    s.add_pending("x")
    s.clear_pending("x")
    s.save()
    assert SeenStore(p).pending() == []


def test_corrupt_lines_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "seen.jsonl"
    p.write_text('{"uid": "good", "first_seen": 1}\nNOT JSON\n')
    s = SeenStore(p)
    assert s.is_new("good") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.store'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/store.py
"""Durable record of which jobs have already been seen and notified."""
from __future__ import annotations

import json
import logging
import pathlib
import time

log = logging.getLogger(__name__)

PENDING_PREFIX = "pending:"


class SeenStore:
    def __init__(self, path: pathlib.Path | str):
        self.path = pathlib.Path(path)
        self._seen: dict[str, dict] = {}
        self._pending: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # A truncated write must not brick the whole run.
                log.warning("skipping corrupt state line")
                continue
            uid = rec.get("uid")
            if not uid:
                continue
            if uid.startswith(PENDING_PREFIX):
                self._pending.add(uid[len(PENDING_PREFIX):])
            else:
                self._seen[uid] = rec

    def is_new(self, uid: str) -> bool:
        return uid not in self._seen

    def mark(self, uid: str, *, company: str = "", title: str = "",
             first_seen: float | None = None) -> None:
        if uid in self._seen:
            return
        self._seen[uid] = {
            "uid": uid,
            "first_seen": first_seen if first_seen is not None else time.time(),
            "company": company,
            "title": title,
        }

    def seed(self, uids) -> None:
        """Cold start: record without notifying."""
        for uid in uids:
            self.mark(uid)

    def add_pending(self, uid: str) -> None:
        """A job whose notification failed; retried next run."""
        self._pending.add(uid)

    def clear_pending(self, uid: str) -> None:
        self._pending.discard(uid)

    def pending(self) -> list[str]:
        return sorted(self._pending)

    def prune(self, max_age_days: int = 120) -> int:
        cutoff = time.time() - max_age_days * 86400
        before = len(self._seen)
        self._seen = {
            u: r for u, r in self._seen.items()
            if r.get("first_seen", 0) >= cutoff
        }
        return before - len(self._seen)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r, ensure_ascii=False) for r in self._seen.values()]
        lines += [
            json.dumps({"uid": f"{PENDING_PREFIX}{u}", "first_seen": time.time()})
            for u in sorted(self._pending)
        ]
        # Atomic replace: a half-written state file is worse than a stale one.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(self.path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/store.py tests/test_store.py
git commit -m "feat: add seen-state store with pending retry queue"
```

---

## Task 15: Telegram notifier

**Files:**
- Create: `src/jobfinder/notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notify.py
import httpx
import respx

from jobfinder.model import Job
from jobfinder.notify import TelegramNotifier, format_message

API = "https://api.telegram.org/botTOKEN/sendMessage"


def mk(**kw):
    base = dict(ats="greenhouse", token="jfrog", job_id="1", company="JFrog",
                title="Backend Engineer", location="Tel Aviv, Israel",
                url="https://jfrog.com/job/1", description="Great job")
    base.update(kw)
    return Job(**base)


def test_message_contains_key_fields():
    msg = format_message(mk())
    assert "JFrog" in msg
    assert "Backend Engineer" in msg
    assert "Tel Aviv, Israel" in msg
    assert "https://jfrog.com/job/1" in msg


def test_message_escapes_html_special_characters():
    """A title with & or < would break Telegram HTML parse mode."""
    msg = format_message(mk(title="R&D <Backend> Engineer"))
    assert "&amp;" in msg
    assert "<Backend>" not in msg


@respx.mock
async def test_send_posts_to_telegram():
    route = respx.post(API).mock(return_value=httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient() as c:
        n = TelegramNotifier("TOKEN", "123")
        assert await n.send(c, mk()) is True
    assert route.called
    body = route.calls[0].request.content.decode()
    assert "123" in body


@respx.mock
async def test_send_returns_false_on_failure():
    """A failed send must be reported so the job is not marked seen."""
    respx.post(API).mock(return_value=httpx.Response(400, json={"ok": False}))
    async with httpx.AsyncClient() as c:
        n = TelegramNotifier("TOKEN", "123")
        assert await n.send(c, mk()) is False


@respx.mock
async def test_send_returns_false_on_network_error():
    respx.post(API).mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as c:
        n = TelegramNotifier("TOKEN", "123")
        assert await n.send(c, mk()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_notify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.notify'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/notify.py
"""Telegram delivery."""
from __future__ import annotations

import html
import logging

import httpx

from jobfinder.model import Job

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"


def format_message(job: Job) -> str:
    """Telegram HTML-parse-mode message. All interpolated text is escaped."""
    title = html.escape(job.title)
    company = html.escape(job.company)
    location = html.escape(job.location)
    posted = job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "unknown"
    return (
        f"<b>{title}</b>\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🗓 posted {posted}\n"
        f"\n{html.escape(job.url)}"
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, client: httpx.AsyncClient, job: Job) -> bool:
        """Return True only on confirmed delivery.

        The caller must not mark a job seen when this returns False.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": format_message(job),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp = await client.post(
                API.format(token=self.bot_token), json=payload, timeout=20.0
            )
            if resp.status_code != 200:
                log.error("telegram %s: %s", resp.status_code, resp.text[:200])
                return False
            return bool(resp.json().get("ok"))
        except Exception as exc:  # noqa: BLE001
            log.error("telegram send failed: %s", exc)
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_notify.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/jobfinder/notify.py tests/test_notify.py
git commit -m "feat: add Telegram notifier"
```

---

## Task 16: Config and the verified seed registry

**Files:**
- Create: `src/jobfinder/config.py`, `registry/companies.yaml`, `config/profile.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write `registry/companies.yaml`**

Every entry below was verified live on 2026-11-22. `il_verified: true` means the board
had at least one Israeli posting at verification time. Entries with `il_verified: false`
are confirmed-correct boards that simply had no Israeli opening that day — they are kept
deliberately, because a company with no opening today is exactly who to watch tomorrow.

```yaml
# company → ATS board. Verified 2026-11-22.
companies:
  - {name: Wiz,                ats: greenhouse,      token: wizinc,           il_verified: true}
  - {name: Cato Networks,      ats: greenhouse,      token: catonetworks,     il_verified: true}
  - {name: AppsFlyer,          ats: greenhouse,      token: appsflyer,        il_verified: true}
  - {name: Similarweb,         ats: greenhouse,      token: similarweb,       il_verified: true}
  - {name: Payoneer,           ats: greenhouse,      token: payoneer,         il_verified: true}
  - {name: JFrog,              ats: greenhouse,      token: jfrog,            il_verified: true}
  - {name: Riskified,          ats: greenhouse,      token: riskified,        il_verified: true}
  - {name: Taboola,            ats: greenhouse,      token: taboola,          il_verified: true}
  - {name: Via,                ats: greenhouse,      token: via,              il_verified: true}
  - {name: NICE,               ats: greenhouse,      token: nice,             il_verified: true}
  - {name: Gong,               ats: greenhouse,      token: gongio,           il_verified: true}
  - {name: Aidoc,              ats: greenhouse,      token: aidocmedical,     il_verified: true}
  - {name: Tipalti,            ats: greenhouse,      token: tipaltisolutions, il_verified: true}
  - {name: Transmit Security,  ats: greenhouse,      token: transmitsecurity, il_verified: true}
  - {name: Forter,             ats: greenhouse,      token: forter,           il_verified: true}
  - {name: Yotpo,              ats: greenhouse,      token: yotpo,            il_verified: true}
  - {name: Axonius,            ats: greenhouse,      token: axonius,          il_verified: true}
  - {name: Orca Security,      ats: greenhouse,      token: orcasecurity,     il_verified: true}
  - {name: Apiiro,             ats: greenhouse,      token: apiiro,           il_verified: true}
  - {name: BigID,              ats: greenhouse,      token: bigid,            il_verified: true}
  - {name: Island,             ats: greenhouse,      token: island,           il_verified: true}
  - {name: Torq,               ats: greenhouse,      token: torq,             il_verified: true}
  - {name: Salt Security,      ats: greenhouse,      token: saltsecurity,     il_verified: true}
  - {name: Optimove,           ats: greenhouse,      token: optimove,         il_verified: true}
  - {name: Augury,             ats: greenhouse,      token: augury,           il_verified: true}
  - {name: Lemonade,           ats: ashby,           token: lemonade,         il_verified: true}
  - {name: Moon Active,        ats: ashby,           token: moonactive,       il_verified: true}
  - {name: Simply,             ats: ashby,           token: simply,           il_verified: true}
  - {name: HoneyBook,          ats: ashby,           token: honeybook,        il_verified: true}
  - {name: Finout,             ats: ashby,           token: finout,           il_verified: true}
  - {name: Redis,              ats: ashby,           token: redis,            il_verified: true}
  - {name: Sweep,              ats: ashby,           token: sweep,            il_verified: true}
  - {name: Singular,           ats: ashby,           token: singular,         il_verified: true}
  - {name: Unit,               ats: ashby,           token: unit,             il_verified: true}
  - {name: WalkMe,             ats: lever,           token: walkme,           il_verified: true}
  - {name: Armis,              ats: smartrecruiters, token: armis,            il_verified: true}
  - {name: Kaltura,            ats: smartrecruiters, token: kalturainc,       il_verified: true}
  # Correctly identified boards with no Israeli opening at verification time.
  - {name: Snyk,               ats: ashby,           token: Snyk,             il_verified: false}
  - {name: Verint,             ats: ashby,           token: verint,           il_verified: false}
  - {name: Pagaya,             ats: greenhouse,      token: pagaya,           il_verified: false}
  - {name: Descope,            ats: greenhouse,      token: descope,          il_verified: false}
  - {name: Bringg,             ats: greenhouse,      token: bringg,           il_verified: false}
  - {name: Hibob,              ats: smartrecruiters, token: hibob,            il_verified: false}
  - {name: Fiverr,             ats: smartrecruiters, token: fiverr,           il_verified: false}
```

- [ ] **Step 2: Write `config/profile.yaml`**

```yaml
# Tunables. Edit freely; no code change required.
max_years_experience: 3
state_path: state/seen.jsonl
seen_max_age_days: 120
# Max simultaneous outbound HTTP requests.
concurrency: 12
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_config.py
import pytest

from jobfinder.adapters import ADAPTERS
from jobfinder.config import load_profile, load_registry


def test_registry_loads_every_company():
    companies = load_registry("registry/companies.yaml")
    assert len(companies) >= 40


def test_every_company_has_required_fields():
    for c in load_registry("registry/companies.yaml"):
        assert c["name"] and c["ats"] and c["token"]


def test_every_registry_ats_has_an_adapter():
    """A typo'd ats name would silently skip a company forever."""
    for c in load_registry("registry/companies.yaml"):
        assert c["ats"] in ADAPTERS, f"{c['name']} -> unknown ats {c['ats']}"


def test_no_duplicate_boards():
    seen = set()
    for c in load_registry("registry/companies.yaml"):
        key = (c["ats"], c["token"])
        assert key not in seen, f"duplicate board {key}"
        seen.add(key)


def test_profile_defaults():
    p = load_profile("config/profile.yaml")
    assert p["max_years_experience"] == 3
    assert p["concurrency"] >= 1


def test_missing_registry_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_registry(tmp_path / "nope.yaml")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.config'`

- [ ] **Step 5: Write the implementation**

```python
# src/jobfinder/config.py
from __future__ import annotations

import pathlib

import yaml


def load_registry(path: str | pathlib.Path) -> list[dict]:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"registry not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("companies", [])


def load_profile(path: str | pathlib.Path) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"profile not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add src/jobfinder/config.py registry/companies.yaml config/profile.yaml tests/test_config.py
git commit -m "feat: add config loading and verified seed registry of 44 boards"
```

---

## Task 17: The Watcher orchestration

**Files:**
- Create: `src/jobfinder/watch.py`
- Test: `tests/test_watch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_watch.py
import httpx
import pytest

from jobfinder.model import Job
from jobfinder.watch import run_once


class FakeAdapter:
    name = "fake"
    needs_detail = False

    def __init__(self, jobs, boom=False):
        self.jobs = jobs
        self.boom = boom

    async def fetch(self, client, token, company):
        if self.boom:
            raise RuntimeError("board exploded")
        return self.jobs

    async def hydrate(self, client, job):
        return job


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, client, job):
        if self.fail:
            return False
        self.sent.append(job)
        return True


def mk(job_id, title="Backend Engineer", location="Tel Aviv, Israel", desc=""):
    return Job(ats="fake", token="t", job_id=job_id, company="C", title=title,
               location=location, url=f"http://x/{job_id}", description=desc)


@pytest.fixture
def registry():
    return [{"name": "C", "ats": "fake", "token": "t"}]


async def test_notifies_matching_new_job(tmp_path, registry):
    n = FakeNotifier()
    await run_once(registry, {"fake": FakeAdapter([mk("1")])}, n,
                   state_path=tmp_path / "s.jsonl")
    assert len(n.sent) == 1


async def test_does_not_renotify_on_second_run(tmp_path, registry):
    adapters = {"fake": FakeAdapter([mk("1")])}
    path = tmp_path / "s.jsonl"
    n1 = FakeNotifier()
    await run_once(registry, adapters, n1, state_path=path)
    n2 = FakeNotifier()
    await run_once(registry, adapters, n2, state_path=path)
    assert len(n1.sent) == 1
    assert len(n2.sent) == 0


async def test_filters_out_senior_and_foreign(tmp_path, registry):
    jobs = [mk("1", title="Senior Backend Engineer"),
            mk("2", location="London, UK"),
            mk("3", title="Account Executive"),
            mk("4", desc="8+ years of experience")]
    n = FakeNotifier()
    await run_once(registry, {"fake": FakeAdapter(jobs)}, n,
                   state_path=tmp_path / "s.jsonl")
    assert n.sent == []


async def test_seed_mode_marks_without_notifying(tmp_path, registry):
    path = tmp_path / "s.jsonl"
    n = FakeNotifier()
    await run_once(registry, {"fake": FakeAdapter([mk("1")])}, n,
                   state_path=path, seed=True)
    assert n.sent == []
    n2 = FakeNotifier()
    await run_once(registry, {"fake": FakeAdapter([mk("1")])}, n2, state_path=path)
    assert n2.sent == [], "seeded jobs must stay suppressed"


async def test_failed_notification_is_retried_not_lost(tmp_path, registry):
    """The whole point: a send failure must not silently swallow a job."""
    path = tmp_path / "s.jsonl"
    adapters = {"fake": FakeAdapter([mk("1")])}
    failing = FakeNotifier(fail=True)
    await run_once(registry, adapters, failing, state_path=path)
    assert failing.sent == []

    working = FakeNotifier()
    await run_once(registry, adapters, working, state_path=path)
    assert len(working.sent) == 1, "job should be retried after a failed send"


async def test_one_broken_board_does_not_abort_the_run(tmp_path):
    registry = [{"name": "Bad", "ats": "boom", "token": "t"},
                {"name": "Good", "ats": "fake", "token": "t"}]
    adapters = {"boom": FakeAdapter([], boom=True),
                "fake": FakeAdapter([mk("1")])}
    n = FakeNotifier()
    await run_once(registry, adapters, n, state_path=tmp_path / "s.jsonl")
    assert len(n.sent) == 1


async def test_unknown_ats_in_registry_is_skipped(tmp_path):
    registry = [{"name": "X", "ats": "nosuch", "token": "t"}]
    n = FakeNotifier()
    await run_once(registry, {}, n, state_path=tmp_path / "s.jsonl")
    assert n.sent == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_watch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobfinder.watch'`

- [ ] **Step 3: Write the implementation**

```python
# src/jobfinder/watch.py
"""The Watcher: poll every board, filter, notify, persist."""
from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib

import httpx

from jobfinder.adapters import ADAPTERS
from jobfinder.config import load_profile, load_registry
from jobfinder.filter import passes_stage_one, passes_stage_two
from jobfinder.model import Job
from jobfinder.notify import TelegramNotifier
from jobfinder.store import SeenStore

log = logging.getLogger(__name__)


async def _collect(client, adapters, entry, sem) -> list[Job]:
    """Fetch one board. Never raises — a bad board must not kill the run."""
    adapter = adapters.get(entry["ats"])
    if adapter is None:
        log.warning("no adapter for ats=%s (%s)", entry["ats"], entry["name"])
        return []
    async with sem:
        try:
            return await adapter.fetch(client, entry["token"], entry["name"])
        except Exception as exc:  # noqa: BLE001
            log.warning("board failed %s/%s: %s",
                        entry["ats"], entry["token"], exc)
            return []


async def run_once(
    registry: list[dict],
    adapters: dict,
    notifier,
    *,
    state_path: pathlib.Path | str = "state/seen.jsonl",
    seed: bool = False,
    concurrency: int = 12,
    client: httpx.AsyncClient | None = None,
) -> dict:
    store = SeenStore(state_path)
    sem = asyncio.Semaphore(concurrency)
    owns_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=True)

    try:
        results = await asyncio.gather(
            *(_collect(client, adapters, e, sem) for e in registry)
        )
        all_jobs = [j for batch in results for j in batch]

        # Cold start: record everything, notify nothing.
        if seed:
            store.seed(j.uid for j in all_jobs)
            store.prune()
            store.save()
            return {"fetched": len(all_jobs), "seeded": len(all_jobs), "sent": 0}

        by_uid = {j.uid: j for j in all_jobs}
        # Jobs whose notification failed previously get another chance.
        retry = [by_uid[u] for u in store.pending() if u in by_uid]
        fresh = [j for j in all_jobs if store.is_new(j.uid)]

        candidates = {j.uid: j for j in (*retry, *fresh)}.values()
        stage_one = [j for j in candidates if passes_stage_one(j)]

        # Only pay for detail requests on jobs that already look relevant.
        hydrated = []
        for job in stage_one:
            adapter = adapters.get(job.ats)
            if adapter is not None and getattr(adapter, "needs_detail", False):
                async with sem:
                    try:
                        job = await adapter.hydrate(client, job)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("hydrate failed %s: %s", job.uid, exc)
            hydrated.append(job)

        matches = [j for j in hydrated if passes_stage_two(j)]

        sent = 0
        for job in matches:
            ok = await notifier.send(client, job)
            if ok:
                sent += 1
                store.mark(job.uid, company=job.company, title=job.title)
                store.clear_pending(job.uid)
            else:
                # Never mark seen on failure, or the job is lost forever.
                store.add_pending(job.uid)

        # Non-matching jobs are recorded so they are not re-filtered each run.
        matched = {j.uid for j in matches}
        for job in all_jobs:
            if job.uid not in matched:
                store.mark(job.uid, company=job.company, title=job.title)

        store.prune()
        store.save()
        return {"fetched": len(all_jobs), "candidates": len(stage_one),
                "matched": len(matches), "sent": sent}
    finally:
        if owns_client:
            await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Poll ATS boards for junior roles.")
    ap.add_argument("--seed", action="store_true",
                    help="record all current jobs as seen without notifying")
    ap.add_argument("--registry", default="registry/companies.yaml")
    ap.add_argument("--profile", default="config/profile.yaml")
    args = ap.parse_args()

    import os

    profile = load_profile(args.profile)
    registry = load_registry(args.registry)
    notifier = TelegramNotifier(
        os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    )
    stats = asyncio.run(
        run_once(
            registry, ADAPTERS, notifier,
            state_path=profile.get("state_path", "state/seen.jsonl"),
            seed=args.seed,
            concurrency=profile.get("concurrency", 12),
        )
    )
    log.info("run complete: %s", stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_watch.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/jobfinder/watch.py tests/test_watch.py
git commit -m "feat: add Watcher orchestration with seed mode and retry queue"
```

---

## Task 18: Live smoke test against the real registry

**Files:**
- Create: `scripts/smoke.py`

This is the first proof the system works against production APIs rather than fixtures.

- [ ] **Step 1: Write the smoke script**

```python
# scripts/smoke.py
"""Hit the real registry and print what WOULD be sent. Sends nothing."""
import asyncio
import logging

from jobfinder.adapters import ADAPTERS
from jobfinder.config import load_registry
from jobfinder.filter import passes_stage_one, passes_stage_two
from jobfinder.watch import run_once


class DryRunNotifier:
    def __init__(self):
        self.sent = []

    async def send(self, client, job):
        self.sent.append(job)
        print(f"  [{job.company}] {job.title} — {job.location}\n    {job.url}")
        return True


async def main():
    logging.basicConfig(level=logging.WARNING)
    registry = load_registry("registry/companies.yaml")
    print(f"polling {len(registry)} boards...\n")
    n = DryRunNotifier()
    stats = await run_once(
        registry, ADAPTERS, n, state_path="/tmp/jobfinder_smoke.jsonl"
    )
    print(f"\n{stats}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it**

Run: `rm -f /tmp/jobfinder_smoke.jsonl && uv run python scripts/smoke.py`

Expected: a `polling 44 boards...` line, then zero or more matching jobs, then a stats
dict where `fetched` is in the high hundreds or low thousands. If `fetched` is 0, the
registry or adapters are broken — stop and debug before continuing.

- [ ] **Step 3: Sanity-check the output by hand**

Confirm every printed job is (a) in Israel, (b) not senior, (c) backend or data. If any
printed job violates one of these, add a failing test for that exact title or location to
the relevant `tests/test_filter_*.py` file, then fix the rule.

- [ ] **Step 4: Verify the second run is quiet**

Run: `uv run python scripts/smoke.py`
Expected: the same `fetched` count, but no job lines — everything is already seen.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke.py
git commit -m "test: add live dry-run smoke script"
```

---

## Task 19: GitHub Actions workflow and state branch

**Files:**
- Create: `.github/workflows/watch.yml`

State lives on an orphan `state` branch so `main` stays free of 96 automated commits
per day.

- [ ] **Step 1: Create the orphan state branch**

```bash
git checkout --orphan state
git rm -rf --cached . >/dev/null 2>&1 || true
mkdir -p state && : > state/seen.jsonl
printf 'Automated state branch. Do not edit by hand.\n' > README.md
git add state/seen.jsonl README.md
git commit -m "chore: initialize state branch"
git checkout main
```

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/watch.yml
name: watch

on:
  schedule:
    # Every 15 minutes. GitHub cron is best-effort and drifts under load.
    - cron: "*/15 * * * *"
  workflow_dispatch:
    inputs:
      seed:
        description: "Seed mode: record all current jobs without notifying"
        type: boolean
        default: false

concurrency:
  # Never let a slow run overlap the next tick and double-send.
  group: watch
  cancel-in-progress: false

jobs:
  watch:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    # Required to push the updated state file back to the state branch.
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - name: Check out state branch into ./state
        uses: actions/checkout@v4
        with:
          ref: state
          path: .state-branch

      - name: Restore state file
        run: |
          mkdir -p state
          cp .state-branch/state/seen.jsonl state/seen.jsonl 2>/dev/null || : > state/seen.jsonl
          wc -l state/seen.jsonl

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install
        run: pip install -e .

      - name: Run watcher
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          SEED: ${{ github.event.inputs.seed }}
        run: |
          if [ "$SEED" = "true" ]; then
            python -m jobfinder.watch --seed
          else
            python -m jobfinder.watch
          fi

      - name: Persist state
        run: |
          cp state/seen.jsonl .state-branch/state/seen.jsonl
          cd .state-branch
          git config user.name "jobfinder-bot"
          git config user.email "jobfinder-bot@users.noreply.github.com"
          if ! git diff --quiet; then
            git add state/seen.jsonl
            git commit -m "state: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
            git push origin state
          else
            echo "no state change"
          fi
```

- [ ] **Step 3: Validate the workflow parses**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/watch.yml')); print('valid')"`
Expected: `valid`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/watch.yml
git commit -m "ci: add 15-minute watch workflow with state-branch persistence"
```

---

## Task 20: README and first live deployment

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

````markdown
# JobFinder

Polls the ATS job boards of Israeli hi-tech companies every 15 minutes and pushes
matching junior backend / data roles to Telegram, usually before they reach LinkedIn.

## How it works

Israeli hi-tech companies run on ATS platforms (Greenhouse, Ashby, Lever,
SmartRecruiters), each of which exposes a public JSON API. The ATS API is the careers
page's backend, so a posting is visible there the moment it goes live.

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather); copy the token.
2. Message your new bot once, then get your chat id from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. In the repo: Settings → Secrets and variables → Actions, add
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. Run the workflow once in **seed mode** (Actions → watch → Run workflow → seed ✓).
   This records all existing jobs so you are not flooded on first run.
5. After seeding completes, the 15-minute schedule takes over.

## Local use

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest -q                    # run the test suite
uv run python scripts/smoke.py      # dry run: print matches, send nothing
```

## Tuning

- `config/profile.yaml` — experience ceiling, concurrency, state location.
- `registry/companies.yaml` — the company list.
- `src/jobfinder/filter.py` — the matching rules.

## Coverage

Phase 1 covers 44 verified boards on four ATS platforms. Many large Israeli employers
(Monday, Wix, Rapyd, CyberArk, Checkmarx, Playtika, Mobileye) use **Comeet**, which is
not yet supported — that is the single biggest coverage win and is Phase 3.
````

- [ ] **Step 2: Commit and push**

```bash
git add README.md
git commit -m "docs: add README with setup instructions"
git push -u origin main
git push origin state
```

- [ ] **Step 3: Configure secrets**

In the GitHub repo UI add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` under
Settings → Secrets and variables → Actions.

- [ ] **Step 4: Run seed mode**

Actions → watch → Run workflow → check `seed` → Run.
Expected: the run succeeds, logs `seeded: <N>` with N in the hundreds or thousands, and
pushes one commit to the `state` branch. **No Telegram messages arrive.**

- [ ] **Step 5: Verify the live schedule**

Wait for the next scheduled run (up to ~20 minutes given cron drift).
Expected: the run succeeds and `sent` is 0 or a small number. Any Telegram message that
arrives should be a genuine junior Israeli backend/data role.

- [ ] **Step 6: Final verification**

Run: `uv run pytest -q`
Expected: the full suite passes.

---

## Done When

- `uv run pytest -q` passes with no failures.
- `scripts/smoke.py` prints only Israeli, non-senior, backend/data roles.
- The `watch` workflow runs green on schedule.
- Seed mode has run once and the `state` branch holds a non-empty `seen.jsonl`.
- A real new posting produces a Telegram message within ~20 minutes of publication.

## Explicitly Out of Scope for Phase 1

These are planned for later phases and must not be built here:

- The Prospector and automated company discovery (Phase 2).
- Dead-board tracking (`status: dead` after three consecutive failures). The spec
  defines it, but it only pays off once the Prospector exists to re-discover those
  companies, so it ships with Phase 2. In Phase 1 a dead board simply logs a warning
  and yields no jobs.
- Comeet, Workday, Workable, Recruitee, Breezy, Teamtailor adapters (Phase 3).
- Claude-based fit scoring against the CV (Phase 4).
