import pytest

from jobfinder.adapters import ADAPTERS, get_adapter


def test_all_four_adapters_registered():
    assert set(ADAPTERS) == {"greenhouse", "ashby", "lever", "smartrecruiters"}


@pytest.mark.parametrize("name", ["greenhouse", "ashby", "lever", "smartrecruiters"])
def test_adapter_name_matches_key(name):
    assert get_adapter(name).name == name


def test_only_smartrecruiters_needs_detail():
    assert get_adapter("smartrecruiters").needs_detail is True
    for name in ("greenhouse", "ashby", "lever"):
        assert get_adapter(name).needs_detail is False


def test_unknown_adapter_raises():
    with pytest.raises(KeyError):
        get_adapter("workday")
