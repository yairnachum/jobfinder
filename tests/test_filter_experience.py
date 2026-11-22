import pytest

from jobfinder.filter import min_years, passes_stage_one, passes_stage_two
from jobfinder.model import Job


def mk(title="Backend Engineer", location="Tel Aviv, Israel",
       description="", country=None):
    return Job(ats="x", token="t", job_id="1", company="C", title=title,
               location=location, url="u", description=description,
               country=country)


@pytest.mark.parametrize("text,expected", [
    ("5+ years of experience", 5),
    ("3-5 years of experience", 3),
    ("at least 4 years experience", 4),
    ("minimum of 2 years", 2),
    ("2+ yrs experience", 2),
    ("1 year of experience", 1),
    ("7 years' experience in backend", 7),
    ("3 שנות ניסיון", 3),
    ("לפחות 5 שנות ניסיון", 5),
])
def test_extracts_minimum_years(text, expected):
    assert min_years(text) == expected


def test_returns_none_when_no_requirement_stated():
    assert min_years("We are looking for a great engineer.") is None


def test_picks_the_lowest_requirement_when_several_appear():
    """Descriptions list several stacks; the lowest bar is the real entry bar."""
    assert min_years("5+ years in Java. 2+ years with Python.") == 2


def test_ignores_unrelated_numbers():
    assert min_years("We are a team of 200 people founded 10 years ago") is None


def test_stage_one_accepts_junior_israeli_backend():
    assert passes_stage_one(mk()) is True


def test_stage_one_rejects_foreign():
    assert passes_stage_one(mk(location="London, UK")) is False


def test_stage_one_rejects_senior():
    assert passes_stage_one(mk(title="Senior Backend Engineer")) is False


def test_stage_one_rejects_out_of_family():
    assert passes_stage_one(mk(title="Account Executive")) is False


def test_stage_two_accepts_zero_to_three_years():
    assert passes_stage_two(mk(description="2+ years of experience")) is True


def test_stage_two_rejects_four_plus_years():
    assert passes_stage_two(mk(description="4+ years of experience")) is False


def test_stage_two_accepts_when_experience_unstated():
    """Moderate setting: silence is not a rejection."""
    assert passes_stage_two(mk(description="Join our team!")) is True


def test_stage_two_accepts_empty_description():
    assert passes_stage_two(mk(description="")) is True
