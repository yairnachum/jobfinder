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
