import pytest

from jobfinder.filter import (is_junior, passes_stage_one, passes_stage_two,
                              required_years)
from jobfinder.model import Job


def mk(title="Backend Engineer", location="Tel Aviv, Israel",
       description="", country=None):
    return Job(ats="x", token="t", job_id="1", company="C", title=title,
               location=location, url="u", description=description,
               country=country)


@pytest.mark.parametrize("text,expected", [
    ("3+ years of professional experience", 3),
    ("3-5 years of experience", 3),
    ("at least 4 years experience", 4),
    ("minimum of 2 years", 2),
    ("must have 3 years of experience", 3),
    ("2+ yrs experience", 2),
    ("1-2 years of hands-on software development", 1),
    ("לפחות 5 שנות ניסיון", 5),
])
def test_extracts_stated_requirement(text, expected):
    assert required_years(text) == expected


def test_takes_the_highest_requirement_not_the_lowest():
    """A posting asking 4 years somewhere and 2 elsewhere is a 4-year role.
    Taking the minimum let mid-level jobs through as junior."""
    assert required_years("2+ years with Python. At least 4 years of SQL.") == 4


def test_returns_none_when_nothing_stated():
    assert required_years("We are looking for a great engineer.") is None


def test_ignores_unrelated_numbers():
    assert required_years("a team of 200 people founded 10 years ago") is None


@pytest.mark.parametrize("text", [
    "Junior Data Scientist", "Software Engineer Intern", "Entry Level Developer",
    "Graduate Software Engineer", "Student - Backend", "New Grad SWE",
    "סטודנט לתוכנה", "משרת מתמחה", "No prior experience required",
])
def test_junior_markers_detected(text):
    assert is_junior(text) is True


def test_ordinary_title_is_not_junior():
    assert is_junior("Backend Engineer") is False


# --- the rule the user asked for: 0 years or student ---

def test_rejects_three_plus_years():
    """'3+' means a minimum of three. This was the main source of noise."""
    assert passes_stage_two(mk(description="3+ years of experience")) is False


def test_rejects_two_plus_years():
    assert passes_stage_two(mk(description="2+ years of experience")) is False


def test_accepts_one_year():
    assert passes_stage_two(mk(description="1+ years of experience")) is True


def test_accepts_explicit_junior_title():
    assert passes_stage_two(mk(title="Junior Backend Engineer")) is True


def test_accepts_student_and_intern_roles():
    assert passes_stage_two(mk(title="Software Engineer Intern")) is True
    assert passes_stage_two(mk(title="Student - Backend Developer")) is True


def test_rejects_when_experience_unstated_and_not_labelled_junior():
    """Silence used to mean acceptance and was the largest noise source."""
    assert passes_stage_two(mk(description="Join our team!")) is False


def test_junior_label_does_not_override_a_real_experience_bar():
    assert passes_stage_two(
        mk(title="Junior Engineer", description="5+ years of experience")) is False


def test_stage_one_still_screens_title_and_location():
    assert passes_stage_one(mk()) is True
    assert passes_stage_one(mk(location="London, UK")) is False
    assert passes_stage_one(mk(title="Senior Backend Engineer")) is False
    assert passes_stage_one(mk(title="Account Executive")) is False
