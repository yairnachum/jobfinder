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

# The country named explicitly, as opposed to a city that merely sits in it.
_IL_COUNTRY_RE = re.compile(r"(?<![a-z])(israel|ישראל)(?![a-z])", re.I)

# Foreign markers, used only to disqualify a city-only match.
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
    # The country named outright wins, even alongside a foreign office: a
    # multi-site posting like "Tel Aviv, Israel; New York" is open in Israel,
    # and missing a real opening costs more than an occasional stray one.
    if _IL_COUNTRY_RE.search(text):
        return True
    # Only a city name matched, and those can collide with foreign places
    # ("Tel Aviv Street, London"), so a foreign marker disqualifies it.
    return not _FOREIGN_RE.search(text)


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


MAX_YEARS = 2  # Junior territory. 3+ years is mid-level and was the noise.

_UNITS = r"(?:years?|yrs?|שנות|שנים)"

# Explicit junior/student markers. These are the positive evidence the filter
# now requires, rather than merely inferring juniority from silence.
_JUNIOR_RE = re.compile(
    r"\b("
    r"junior|jr\.?|entry[\s-]?level|entry|graduate|new\s+grad|fresh\s+grad|"
    r"student|intern|internship|trainee|apprentice|rotation|"
    r"no\s+(?:prior\s+)?experience(?:\s+required)?|"
    r"ג'וניור|גוניור|סטודנט|סטודנטים|מתמחה|התמחות|ללא\s+ניסיון"
    r")\b",
    re.I,
)

# A stated requirement: "3+ years", "3-5 years", "at least 4 years",
# "minimum of 2 years", "must have 3 years".
_REQ_PATTERNS = (
    # "N+ years" / "N-M years" / "N years ... experience"
    re.compile(r"(\d{1,2})\s*\+\s*" + _UNITS, re.I),
    re.compile(r"(\d{1,2})\s*-\s*\d{1,2}\s*" + _UNITS, re.I),
    re.compile(r"(?:at\s+least|minimum\s+of|minimum|min\.|over|more\s+than|"
               r"must\s+have|requires?|required:?|לפחות)\s*"
               r"(\d{1,2})\s*\+?\s*" + _UNITS, re.I),
    # The lookbehind stops this matching the UPPER bound of a range: in
    # "3-5 years" the requirement is 3, and max() would otherwise pick 5.
    re.compile(r"(?<![-\d])(\d{1,2})\s*" + _UNITS +
               r"[^.\n]{0,30}?(?:experience|ניסיון)", re.I),
)


def required_years(description: str) -> int | None:
    """Highest stated years-of-experience requirement, or None.

    Deliberately the HIGHEST, not the lowest. A posting that says "at least 4
    years" somewhere and "2 years" elsewhere is a 4-year role; taking the
    minimum let mid-level jobs through as junior.
    """
    if not description:
        return None
    found = [
        int(m.group(1))
        for pattern in _REQ_PATTERNS
        for m in pattern.finditer(description)
    ]
    found = [n for n in found if 0 <= n <= 20]
    return max(found) if found else None


def is_junior(text: str) -> bool:
    """True when the text explicitly marks the role as junior or student."""
    return bool(_JUNIOR_RE.search(text or ""))


def passes_stage_one(job: Job) -> bool:
    """Title and location only — cheap, runs before any detail fetch."""
    return (
        is_israel(job)
        and seniority_ok(job.title)
        and role_family(job.title) is not None
    )


def passes_stage_two(job: Job) -> bool:
    """Require positive evidence of a junior or student role.

    An explicit junior/student marker wins unless the posting also demands
    real experience. Otherwise the stated requirement must be at most
    MAX_YEARS. A posting that states nothing and never calls itself junior is
    rejected: silence used to be treated as acceptance and was the single
    largest source of irrelevant alerts.
    """
    years = required_years(job.description)
    if is_junior(job.title) or is_junior(job.description):
        # "Junior ... 5+ years" happens; trust the number over the label,
        # but give a labelled role one year of slack.
        return years is None or years <= MAX_YEARS + 1
    return years is not None and years <= MAX_YEARS
