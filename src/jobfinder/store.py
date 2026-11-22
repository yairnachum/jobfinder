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
