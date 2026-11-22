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
    # Only when "support" qualifies the role itself — an engineering role
    # that merely sits in a support org is still in scope.
    r"support\s+(?:engineer|specialist|representative)|"
    r"technical\s+support|customer\s+support|"
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


MAX_YEARS = 3  # "moderate" setting: 4+ years is out of scope.

_UNITS = r"(?:years?|yrs?|שנות|שנים)"

# "5 years of experience", "3 שנות ניסיון" — a span followed by an
# experience word. The gap is bounded so it cannot leap across a sentence.
_RE_YEARS_EXP = re.compile(
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*" + _UNITS +
    r"[^.\n]{0,24}?(?:experience|exp\b|ניסיון)",
    re.I,
)
# "minimum of 2 years", "at least 4 years" — a qualifier makes it a
# requirement even with no "experience" word.
_RE_QUALIFIED = re.compile(
    r"(?:at\s+least|minimum\s+of|minimum|min\.|over|more\s+than|לפחות)\s*"
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*" + _UNITS,
    re.I,
)
# "2+ years" — an explicit plus is a requirement on its own. This is what
# distinguishes "2+ years with Python" from "founded 10 years ago".
_RE_PLUS = re.compile(r"(\d{1,2})\s*\+\s*" + _UNITS, re.I)

_YEARS_PATTERNS = (_RE_YEARS_EXP, _RE_QUALIFIED, _RE_PLUS)


def min_years(description: str) -> int | None:
    """Lowest stated years-of-experience requirement, or None.

    Descriptions often list several stacks with different bars; the lowest is
    the real entry requirement. A bare "N years" with neither a qualifier nor
    an experience word is ignored, so prose like "founded 10 years ago" does
    not read as a requirement.
    """
    if not description:
        return None
    found = [
        int(m.group(1))
        for pattern in _YEARS_PATTERNS
        for m in pattern.finditer(description)
    ]
    found = [n for n in found if 0 <= n <= 20]
    return min(found) if found else None


def passes_stage_one(job: Job) -> bool:
    """Title and location only — cheap, runs before any detail fetch."""
    return (
        is_israel(job)
        and seniority_ok(job.title)
        and role_family(job.title) is not None
    )


def passes_stage_two(job: Job) -> bool:
    """Description-based checks. Requires a hydrated job."""
    years = min_years(job.description)
    return years is None or years <= MAX_YEARS
