import pytest

from jobfinder.filter import is_israel
from jobfinder.model import Job


def mk(location="", country=None):
    return Job(ats="x", token="t", job_id="1", company="C", title="T",
               location=location, url="u", description="", country=country)


@pytest.mark.parametrize("loc", [
    "Tel Aviv, Israel", "Tel Aviv-Yafo", "TLV", "Herzliya",
    "Israel - Raanana", "Ra'anana", "Haifa", "Jerusalem", "Be'er Sheva",
    "Netanya", "Petah Tikva", "Ramat Gan", "Yokneam", "Rehovot",
    "Airport City", "Tel Aviv District, Israel", "ישראל", "תל אביב",
])
def test_israeli_locations_match(loc):
    assert is_israel(mk(location=loc)) is True


@pytest.mark.parametrize("loc", [
    "London, England, United Kingdom", "New York, NY", "Paris, fr",
    "Toronto, ON", "Remote - US", "Bangalore", "Hawthorne, California",
])
def test_foreign_locations_do_not_match(loc):
    assert is_israel(mk(location=loc)) is False


def test_country_code_wins_over_blank_location():
    assert is_israel(mk(location="", country="IL")) is True


def test_country_code_rejects_when_explicitly_foreign():
    """An explicit foreign ISO code beats a misleading city string."""
    assert is_israel(mk(location="Tel Aviv Street, London", country="GB")) is False


def test_empty_location_without_country_is_not_israel():
    assert is_israel(mk()) is False


def test_city_name_colliding_with_a_foreign_place_is_rejected():
    """A city token alone is weak evidence: 'Tel Aviv Street, London' is in
    London, so a foreign marker disqualifies a city-only match."""
    assert is_israel(mk(location="Tel Aviv Street, London")) is False


def test_israel_named_outright_beats_a_foreign_office():
    """Multi-site postings list several offices. The role IS open in Israel,
    and missing a real opening costs more than an occasional stray one."""
    assert is_israel(mk(location="Tel Aviv, Israel; New York")) is True
    assert is_israel(mk(location="Herzliya, Israel / London, UK")) is True
