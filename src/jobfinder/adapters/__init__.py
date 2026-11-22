"""Adapter dispatch. Adding an ATS means adding one module and one entry here."""
from __future__ import annotations

from jobfinder.adapters.ashby import Ashby
from jobfinder.adapters.base import Adapter
from jobfinder.adapters.comeet import Comeet
from jobfinder.adapters.greenhouse import Greenhouse
from jobfinder.adapters.lever import Lever
from jobfinder.adapters.smartrecruiters import SmartRecruiters

ADAPTERS: dict[str, Adapter] = {
    a.name: a
    for a in (Greenhouse(), Ashby(), Lever(), SmartRecruiters(), Comeet())
}


def get_adapter(name: str) -> Adapter:
    return ADAPTERS[name]


__all__ = ["ADAPTERS", "get_adapter", "Adapter"]
