"""Config and registry loading."""
from __future__ import annotations

import pathlib

import yaml


def load_registry(path: str | pathlib.Path) -> list[dict]:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"registry not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("companies", [])


def load_profile(path: str | pathlib.Path) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"profile not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
