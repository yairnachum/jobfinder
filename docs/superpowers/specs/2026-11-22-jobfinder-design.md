# JobFinder — Design Spec

**Date:** 2026-11-22
**Status:** Approved
**Owner:** Yair Nachum

## Problem

Junior hi-tech roles in Israel are filled fast. Job boards (LinkedIn, AllJobs, Drushim)
lag company career pages by hours or days, so by the time a posting appears there the
applicant pile is already deep. The goal is to learn about relevant openings within
minutes of publication, across as much of the Israeli hi-tech market as possible.

## Core Insight

Israeli hi-tech companies do not hand-build career pages. They run on an Applicant
Tracking System (ATS), and every major ATS exposes a **public, unauthenticated JSON API**
for its job boards. The ATS API is the career page's backend — a posting is live in the
API before the career page even renders it.

This reduces "scrape 1,000 company websites" to "poll ~10 JSON APIs with 1,000 tokens."

### Validation performed (2026-11-22)

Live probes against real Israeli companies confirmed the approach:

| Company | ATS | Board token | Live jobs |
|---|---|---|---|
| JFrog | Greenhouse | `jfrog` | 78 |
| Cato Networks | Greenhouse | `catonetworks` | 120 |
| Riskified | Greenhouse | `riskified` | 45 |
| Gong | Greenhouse | `gongio` | 84 |
| SimilarWeb | Greenhouse | `similarweb` | 59 (14 in Israel) |
| Lemonade | Ashby | `lemonade` | 43 |
| Fiverr | SmartRecruiters | `fiverr` | 3 |
| Armis | SmartRecruiters | `armis` | 2 |

Greenhouse payloads include `title`, `location.name`, `absolute_url`, full `content`
(HTML description), `first_published` and `updated_at` — everything needed for filtering
and notification.

Two findings that shape the design:

1. **Naive HTML scraping of career pages fails.** 5 of 6 tested career pages are
   JS-rendered SPAs that inject the ATS widget at runtime; a plain HTML fetch shows no
   ATS fingerprint. Discovery cannot rely on fetching the careers URL.
2. **Slug collisions are real.** `gong` on SmartRecruiters is a different company than
   `gongio` on Greenhouse (the real Gong). Every discovered board must be verified
   against the company name in the payload before entering the registry.

## Rejected Alternatives

| Approach | Why rejected |
|---|---|
| Per-company HTML scrapers | 1,000 bespoke parsers; breaks on every site redesign; unmaintainable. |
| Scraping LinkedIn / AllJobs / Drushim | Defeats the core premise — aggregators lag company sites. Also aggressively anti-scraping. |
| Paid aggregator APIs | Cost, and still downstream of the ATS. |

## Requirements

Confirmed with the user:

- **Role families:** Backend / Full-stack, and Data / ML / AI.
- **Seniority:** Moderate filter — include explicit junior/entry/graduate/student roles,
  roles asking 0–3 years, and roles with no stated experience. Exclude explicit
  senior/staff/principal/lead/manager roles and anything asking 4+ years.
- **Location:** Anywhere in Israel.
- **Notification:** Telegram bot, one message per matching job, with apply link.
- **Hosting:** GitHub Actions scheduled cron, every 15 minutes.
- **Matching:** Rules/keyword pass first, then Claude scores survivors against the user's CV.
- **Coverage:** Maximum — target 1,000+ companies across all ATS platforms.

## Architecture

Two independent programs with different cadences and failure modes.

### 1. The Prospector (weekly, slow, heavy)

Builds and maintains `registry/companies.yaml`, the `company → ATS + board token` map.
This registry is the project's core asset; coverage is determined entirely by its quality.

Layered discovery, each layer catching what the previous one misses:

1. **Slug probing** — generate candidate slugs from company name and domain, probe all
   ATS APIs. Cheap (one HTTP call per ATS per candidate) and validated to work.
2. **Headless browser network inspection** — load the careers page in Chrome, capture
   outbound XHR/fetch requests, match against known ATS API hostnames. Catches the
   JS-injected widgets that layer 1 and HTML grep both miss (Comeet, Workday).
3. **CNAME resolution** — `careers.<domain>` and `jobs.<domain>` frequently CNAME
   directly to the ATS host.
4. **Name verification** — every candidate board must have a payload company name
   matching the expected company before it is written to the registry. Non-matching
   and zero-job boards are quarantined for manual review, not silently accepted.

**Company list sources** (union, deduplicated by domain):
- Startup Nation Finder (~9,000 Israeli companies) — returns 403 to plain HTTP clients,
  requires the headless path.
- Wikipedia lists of Israeli technology companies.
- Curated public GitHub lists of Israeli hi-tech employers.
- Reverse enumeration from ATS-side search endpoints that expose a location filter.

### 2. The Watcher (every 15 minutes, fast, parallel)

```
registry/companies.yaml
        ↓
  ATS adapters (parallel, isolated failures)
        ↓
  normalize → Job records
        ↓
  diff vs state/seen.jsonl
        ↓
  rules filter (seniority / location / role family)
        ↓
  Claude fit scoring vs CV
        ↓
  Telegram notification
        ↓
  update state/seen.jsonl
```

## Components

```
jobfinder/
  pyproject.toml
  src/jobfinder/
    model.py            # normalized Job dataclass
    config.py           # profile + thresholds loading
    adapters/
      base.py           # Adapter protocol: fetch(token) -> list[Job]
      greenhouse.py  lever.py  ashby.py  smartrecruiters.py  comeet.py
      workable.py  workday.py  recruitee.py  breezy.py  teamtailor.py
    discovery/
      sources.py        # company list acquisition
      slug_probe.py     # layer 1
      headless.py       # layer 2
      cname.py          # layer 3
    filter.py           # rules pass
    scorer.py           # Claude fit scoring
    notify.py           # Telegram
    store.py            # seen-state persistence
    watch.py            # entry point: the Watcher
    prospect.py         # entry point: the Prospector
  registry/companies.yaml
  config/profile.yaml   # CV text, keywords, score threshold
  .github/workflows/watch.yml
  .github/workflows/prospect.yml
  tests/
    fixtures/           # recorded real API payloads
```

### `model.py`

Normalized `Job`:

```
uid          sha1(f"{ats}:{token}:{job_id}")  — stable primary key
company      str
title        str
location     str
url          str          — direct apply link
description  str          — plain text, HTML stripped
posted_at    datetime | None
ats          str
raw          dict         — original payload, retained for debugging
```

`uid` is derived from the ATS-assigned job id, not the title, so title edits by the
employer do not resurface a job as new.

### `adapters/`

One module per ATS, all satisfying `fetch(token) -> list[Job]`. Adding support for a new
ATS is a single new file plus a registry entry. Endpoints:

| ATS | Endpoint | Status |
|---|---|---|
| Greenhouse | `GET boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true` | validated |
| Ashby | `GET api.ashbyhq.com/posting-api/job-board/{t}` | validated |
| SmartRecruiters | `GET api.smartrecruiters.com/v1/companies/{t}/postings` | validated |
| Lever | `GET api.lever.co/v0/postings/{t}?mode=json` | format known, needs live token |
| Comeet | `GET www.comeet.co/careers-api/2.0/company/{uid}/positions?token={tok}` | endpoint confirmed; public token extracted from careers page |
| Workable | `GET apply.workable.com/api/v1/widget/accounts/{t}?details=true` | to validate |
| Workday | `POST {tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | to validate |
| Recruitee | `GET {t}.recruitee.com/api/offers/` | to validate |
| Breezy | `GET {t}.breezy.hr/json` | to validate |
| Teamtailor | `GET {t}.teamtailor.com/jobs.json` | to validate |

Adapters that return descriptions only on a per-job detail call (SmartRecruiters) fetch
details lazily — only for jobs that survive the rules filter — to bound request volume.

### `filter.py`

Deterministic, no network, fully unit-tested. Order: cheapest rejection first.

- **Exclude by title:** senior, sr., staff, principal, lead, head of, director, VP,
  chief, manager, architect, expert, "team lead", "group lead".
- **Exclude non-engineering:** sales, marketing, HR, finance, legal, customer success,
  account executive, BDR, SDR, recruiter, office manager.
- **Include by role family:**
  - Backend/Full-stack: software engineer, backend, back-end, full stack, fullstack,
    server, developer, SWE, Python, Java, Node, Go, C#, .NET, Ruby.
  - Data/ML/AI: data engineer, data analyst, data scientist, machine learning, ML
    engineer, AI engineer, deep learning, NLP, research engineer, algorithm, analytics.
- **Experience extraction:** regex over the description for `N+ years`, `N-M years`, and
  the Hebrew `שנות ניסיון`. Minimum years ≥ 4 rejects. 0–3 passes. No match passes
  (the "moderate" setting).
- **Location:** must match an Israel token — israel, ישראל, tel aviv, tlv, herzliya,
  ra'anana, haifa, jerusalem, be'er sheva, netanya, petah tikva, ramat gan, rehovot,
  yokneam, caesarea, kfar saba, hod hasharon, airport city, modi'in, migdal haemek,
  ashdod, rishon lezion.

### `scorer.py`

Survivors of the rules pass go to the Claude API with the user's CV and the full job
description, returning a 1–10 fit score plus a one-line rationale. Only jobs scoring at or above the
configured threshold are sent; the threshold defaults to 6 and is tunable in
`config/profile.yaml` once real volume is observable. Volume is a handful of jobs per
day, so cost is negligible. The scorer is behind an interface and is skippable via config, so the system
degrades to rules-only if the API key is absent.

### `store.py`

`state/seen.jsonl` — one record per job: `uid`, `first_seen` epoch, company, title.
Pruned at 120 days. At ~20,000 jobs this is roughly 1.2 MB.

**Persistence on GitHub Actions:** Actions is stateless and its cache can be evicted
without warning, which would cause a full re-notification storm. State is therefore
committed to a dedicated orphan `state` branch — free, durable, and an audit trail,
while keeping `main` free of 96 automated commits per day.

## Known Problems and Their Handling

1. **Cold start.** The first run would see ~20,000 pre-existing jobs as new. A `--seed`
   mode records everything as seen and notifies nothing. Required before the first live run.
2. **Cron drift.** GitHub's scheduler is best-effort and drifts under load; 15 minutes is
   a target, not a guarantee. Still substantially ahead of job boards.
3. **Notification loss.** A job must never be marked seen if its notification failed, or
   it is lost permanently. Notification outcome is recorded separately from discovery;
   failed sends enter a retry queue in state and are retried on the next run.
4. **Dead boards.** Companies change ATS. Three consecutive failed runs mark a registry
   entry `status: dead`; dead entries are reported in the weekly Prospector run rather
   than silently dropped, and the Prospector re-runs discovery for them.
5. **Isolated failures.** One bad board must not abort a run. Every adapter call is
   wrapped with a 15s timeout and 2 retries with backoff; failures are logged per company.
6. **Politeness.** Requests are concurrency-capped and spread across hosts. These are
   public endpoints intended for job board rendering, and polling is modest.

## Testing

Test-driven, per the project's standing practice.

- Real API payloads recorded as fixtures in `tests/fixtures/`; adapter normalization is
  tested against them offline, so the suite needs no network.
- `filter.py` gets dense unit coverage — seniority edge cases, experience-range parsing
  (including Hebrew), location matching, role-family boundaries. This is where silent
  false negatives would hide.
- `store.py` is tested for the dedupe contract and the notification-failure path.
- End-to-end test runs the full pipeline against fixtures with a stubbed notifier.

## Build Order

Each phase is independently useful and verifiable.

1. **Phase 1 — working end to end.** Model, store, the four validated adapters
   (Greenhouse, Ashby, SmartRecruiters, Lever), rules filter, Telegram, GitHub Actions
   workflow. Seeded with ~50 hand-verified companies. Delivers real alerts.
2. **Phase 2 — coverage.** The Prospector and full company-list acquisition, taking the
   registry to 1,000+ companies.
3. **Phase 3 — remaining adapters.** Comeet (highest value for Israel), Workday,
   Workable, Recruitee, Breezy, Teamtailor.
4. **Phase 4 — AI scoring.** Claude fit scoring against the CV.

## Setup Inputs Required From User

- Telegram bot token from @BotFather, and the target chat id.
- CV or background text for the scorer (Phase 4).
- `ANTHROPIC_API_KEY` (Phase 4 only).

All are stored as GitHub Actions secrets, never committed.
