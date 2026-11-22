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
