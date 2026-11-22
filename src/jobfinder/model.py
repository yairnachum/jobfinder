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
