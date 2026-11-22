"""The Watcher: poll every board, filter, notify, persist."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
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
            # Persist after every delivery, not once at the end. If the run is
            # killed mid-batch (Actions timeout, preemption), anything already
            # delivered stays recorded and is not sent to the user twice.
            store.save()

        # Non-matching jobs are recorded so they are not re-filtered each run.
        matched = {j.uid for j in matches}
        for job in all_jobs:
            if job.uid not in matched:
                store.mark(job.uid, company=job.company, title=job.title)
                # It may have been queued for retry on an earlier run and since
                # stopped matching; without this it would stay pending forever.
                store.clear_pending(job.uid)

        store.prune()
        store.save()
        return {"fetched": len(all_jobs), "candidates": len(stage_one),
                "matched": len(matches), "sent": sent}
    finally:
        if owns_client:
            await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx logs the full request URL at INFO, and the Telegram bot token is
    # part of that URL. On a public repo that would publish the token into the
    # Actions log on the first alert ever sent.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description="Poll ATS boards for junior roles.")
    ap.add_argument("--seed", action="store_true",
                    help="record all current jobs as seen without notifying")
    ap.add_argument("--registry", default="registry/companies.yaml")
    ap.add_argument("--profile", default="config/profile.yaml")
    args = ap.parse_args()

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
