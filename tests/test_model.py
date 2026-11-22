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
