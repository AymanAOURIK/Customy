"""Standalone config loader. Deps: stdlib + PyYAML + python-dotenv only."""

from __future__ import annotations

import os
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
    llm = cfg.setdefault("llm", {})
    if os.environ.get("GENERATION_MODEL"):
        llm["generation_model"] = os.environ["GENERATION_MODEL"].strip()
    if os.environ.get("ANALYSIS_MODEL"):
        llm["analysis_model"] = os.environ["ANALYSIS_MODEL"].strip()

    # V3: deployment mode and Supabase config
    mode = os.environ.get("CUSTOMY_MODE", "local").strip().lower()
    cfg["mode"] = mode  # "local" or "saas"
    if mode == "saas":
        cfg["supabase"] = {
            "url": os.environ.get("SUPABASE_URL", ""),
            "anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
            "service_role_key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            "jwt_secret": os.environ.get("SUPABASE_JWT_SECRET", ""),
        }
        cfg["database_url"] = os.environ.get("DATABASE_URL", "")

    return cfg


def load_candidate(path: str | None = None) -> dict:
    candidate_path = Path(path) if path else ROOT / "candidate.yaml"
    with candidate_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
