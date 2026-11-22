"""Hit the real registry and print what WOULD be sent. Sends nothing."""
import asyncio
import logging

from jobfinder.adapters import ADAPTERS
from jobfinder.config import load_registry
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
