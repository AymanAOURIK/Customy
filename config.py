"""Standalone config loader. Deps: stdlib + PyYAML + python-dotenv only."""

from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent


def _resolve_path(value: object) -> str:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return str(path)


def load_config() -> dict:
    load_dotenv(ROOT / ".env")
    with (ROOT / "config.yaml").open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    for key, value in cfg.get("paths", {}).items():
        cfg["paths"][key] = _resolve_path(value)
    return cfg


def load_candidate(path: str | None = None) -> dict:
    candidate_path = Path(path) if path else ROOT / "candidate.yaml"
    with candidate_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
