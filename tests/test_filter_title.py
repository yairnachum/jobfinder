import pytest

from jobfinder.filter import role_family, seniority_ok


@pytest.mark.parametrize("title", [
    "Senior Backend Engineer", "Sr. Software Engineer", "Staff Engineer",
    "Principal Data Scientist", "Backend Team Lead", "Engineering Manager",
    "Head of Data", "Director of Product Engineering", "VP R&D",
    "Software Architect", "Group Lead, Platform", "Chief Technology Officer",
    "Data Engineering Tech Lead",
])
def test_senior_titles_rejected(title):
    assert seniority_ok(title) is False


@pytest.mark.parametrize("title", [
    "Backend Engineer", "Junior Software Engineer", "Software Engineer",
    "Data Analyst", "Entry Level Developer", "Graduate Software Engineer",
    "Student - Backend", "Associate Data Scientist", "Full Stack Developer",
])
def test_junior_and_neutral_titles_accepted(title):
    assert seniority_ok(title) is True


def test_leadership_word_inside_other_word_not_matched():
    """'Leader' must match, but 'Pipeline' must not trip the 'lead' rule."""
    assert seniority_ok("Data Pipeline Engineer") is True


@pytest.mark.parametrize("title,family", [
    ("Backend Engineer", "backend"),
    ("Full Stack Developer", "backend"),
    ("Software Engineer", "backend"),
    ("Python Developer", "backend"),
    ("Data Engineer", "data"),
    ("Data Analyst", "data"),
    ("Machine Learning Engineer", "data"),
    ("AI Engineer", "data"),
    ("Algorithm Engineer", "data"),
    ("NLP Researcher", "data"),
])
def test_role_families_detected(title, family):
    assert role_family(title) == family


@pytest.mark.parametrize("title", [
    "Account Executive", "Sales Development Representative",
    "Marketing Manager", "Recruiter", "Office Manager",
    "Customer Success Manager", "Assistant Controller, Revenues",
    "Compensation & Benefits Manager", "Product Designer",
])
def test_non_engineering_titles_have_no_family(title):
    assert role_family(title) is None


def test_qa_is_not_in_scope_for_phase_one():
    """User selected backend and data only."""
    assert role_family("QA Automation Engineer") is None


@pytest.mark.parametrize("title", [
    "Developer Support Engineer",
    "Technical Support Engineer",
    "Customer Support Specialist",
])
def test_support_roles_are_out_of_scope(title):
    """Support is a different function from backend/data; the user picked
    neither. Matched only when 'support' qualifies the role noun, so an
    engineering role that merely sits in a support org still passes."""
    assert role_family(title) is None


def test_engineering_role_within_a_support_org_still_matches():
    assert role_family("Agentic AI Engineer - Product Support") == "data"
