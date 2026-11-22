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


_SENIOR_RE = re.compile(
    r"\b("
    r"senior|sr\.?|staff|principal|lead|leader|head|director|vp|"
    r"vice\s+president|chief|manager|architect|expert|distinguished|fellow"
    r")\b",
    re.I,
)

_EXCLUDE_FUNCTION_RE = re.compile(
    r"\b("
    r"sales|marketing|recruit\w*|talent|hr\b|human\s+resources|finance|"
    r"controller|legal|counsel|customer\s+success|account\s+executive|"
    r"bdr|sdr|office\s+manager|designer|design|content|copywriter|"
    r"compensation|benefits|procurement|facilities|executive\s+assistant"
    r")\b",
    re.I,
)

_BACKEND_RE = re.compile(
    r"\b("
    r"backend|back[\s-]end|full[\s-]?stack|fullstack|software\s+engineer|"
    r"software\s+developer|swe\b|server[\s-]side|platform\s+engineer|"
    r"python|java\b|node(?:\.js)?|golang|\bgo\b|c#|\.net|ruby|scala|kotlin|"
    r"infrastructure\s+engineer|developer"
    r")\b",
    re.I,
)

_DATA_RE = re.compile(
    r"\b("
    r"data\s+engineer|data\s+analyst|data\s+scientist|big\s+data|"
    r"machine\s+learning|\bml\b|ai\s+engineer|\bai\b|deep\s+learning|"
    r"nlp\b|computer\s+vision|algorithm|research\s+engineer|analytics|"
    r"bi\s+developer|mlops"
    r")\b",
    re.I,
)


def seniority_ok(title: str) -> bool:
    """False when the title is explicitly senior or a leadership role."""
    return not _SENIOR_RE.search(title or "")


def role_family(title: str) -> str | None:
    """Return 'backend', 'data', or None when out of scope."""
    t = title or ""
    if _EXCLUDE_FUNCTION_RE.search(t):
        return None
    # Data is checked first: "Data Engineer" also matches the backend
    # "engineer" pattern, and the more specific family should win.
    if _DATA_RE.search(t):
        return "data"
    if _BACKEND_RE.search(t):
        return "backend"
    return None
