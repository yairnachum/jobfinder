# JobFinder

Polls the ATS job boards of Israeli hi-tech companies every 15 minutes and pushes
matching junior backend / data roles to Telegram, usually before they reach LinkedIn.

## How it works

Israeli hi-tech companies don't hand-build their careers pages — they run on an ATS
(Greenhouse, Ashby, Lever, SmartRecruiters), and every one of those exposes a public
JSON API. The ATS API *is* the careers page's backend, so a posting is visible there
the moment it goes live, before aggregators pick it up.

```
registry/companies.yaml  →  ATS adapters (parallel)  →  normalize to Job
                                                            ↓
                         Telegram  ←  filter  ←  diff against seen state
```

A posting is reported when it is in Israel, not senior, in the backend/full-stack or
data/ML family, and asks for no more than 3 years of experience (postings that state no
experience requirement are included).

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and copy the token.
2. Message your new bot once, then read your chat id from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. In the repo: Settings → Secrets and variables → Actions, add `TELEGRAM_BOT_TOKEN`
   and `TELEGRAM_CHAT_ID`.
4. **Run the workflow once in seed mode** (Actions → watch → Run workflow → tick `seed`).
   This records the ~1,500 currently-open jobs as already seen. Skipping this step means
   your first scheduled run tries to notify you about all of them.
5. After seeding finishes, the 15-minute schedule takes over.

## Local use

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest -q                    # 172 tests, no network needed
uv run python scripts/smoke.py      # dry run against the live boards, sends nothing
```

`scripts/record_fixtures.py` re-records the test fixtures from the live APIs if an ATS
ever changes its payload shape.

## Tuning

| What | Where |
|---|---|
| Experience ceiling, concurrency, state location | `config/profile.yaml` |
| The company list | `registry/companies.yaml` |
| Matching rules (seniority, role families, locations) | `src/jobfinder/filter.py` |

Entries marked `il_verified: false` in the registry are boards that were confirmed to
belong to the right company but had no Israeli opening on the day they were verified.
They are kept deliberately — a company with nothing open today is exactly who you want
to be watching tomorrow.

## State

GitHub Actions is stateless and its cache can be evicted, which would cause a
re-notification storm. Seen-job state therefore lives in `state/seen.jsonl` on a
dedicated orphan `state` branch: durable, free, and it keeps ~96 automated commits a day
out of `main`.

A job is only marked seen once its notification is confirmed delivered. Failed sends go
to a retry queue and are retried on the next run, so a Telegram outage delays alerts
rather than losing them.

## Coverage

Phase 1 covers 44 verified boards across four ATS platforms — a live run currently
fetches ~1,500 postings.

Many large Israeli employers (Monday, Wix, Rapyd, CyberArk, Checkmarx, Playtika,
Mobileye) use **Comeet**, which is not yet supported. That is the single biggest
coverage win available and is planned for Phase 3.

## Roadmap

- **Phase 2** — the Prospector: automated company discovery to take the registry past
  1,000 boards, plus dead-board tracking.
- **Phase 3** — Comeet, Workday, Workable, Recruitee, Breezy, Teamtailor adapters.
- **Phase 4** — Claude-based fit scoring of each match against your CV.
