import pytest

from jobfinder.adapters import ADAPTERS
from jobfinder.config import load_profile, load_registry


def test_registry_loads_every_company():
    companies = load_registry("registry/companies.yaml")
    assert len(companies) >= 40


def test_every_company_has_required_fields():
    for c in load_registry("registry/companies.yaml"):
        assert c["name"] and c["ats"] and c["token"]


def test_every_registry_ats_has_an_adapter():
    """A typo'd ats name would silently skip a company forever."""
    for c in load_registry("registry/companies.yaml"):
        assert c["ats"] in ADAPTERS, f"{c['name']} -> unknown ats {c['ats']}"


def test_no_duplicate_boards():
    seen = set()
    for c in load_registry("registry/companies.yaml"):
        key = (c["ats"], c["token"])
        assert key not in seen, f"duplicate board {key}"
        seen.add(key)


def test_profile_defaults():
    p = load_profile("config/profile.yaml")
    assert p["max_years_experience"] == 2
    assert p["concurrency"] >= 1


def test_missing_registry_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_registry(tmp_path / "nope.yaml")
