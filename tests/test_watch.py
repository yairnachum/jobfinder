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
