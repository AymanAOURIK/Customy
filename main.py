#!/usr/bin/env python3
"""Customy - Resume tailor and job application platform.

Local mode:  python main.py [--port 8765] [--host 127.0.0.1]
SaaS mode:   CUSTOMY_MODE=saas python main.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import os
import shutil
import threading
import webbrowser
from pathlib import Path

from app.db import init_db
from app.profile import build_candidate_context
from app.seeder import seed_answer_bank
from app.server import run_server
from config import load_config

_log = logging.getLogger(__name__)


def _open_browser(url: str) -> None:
    browser_binaries = [
        "wslview",
        "google-chrome",
        "chrome",
        "chromium",
        "chromium-browser",
        "firefox",
        "mozilla",
        "safari",
    ]
    can_open = os.name == "nt" or any(shutil.which(binary) for binary in browser_binaries)
    if not can_open:
        return
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Customy resume tailor")
    parser.add_argument("--port", type=int)
    parser.add_argument("--host")
    args = parser.parse_args()

    cfg = load_config()
    mode = cfg.get("mode", "local")

    # In SaaS mode: bind to 0.0.0.0, use PORT from env, skip browser open
    if mode == "saas":
        host = args.host or "0.0.0.0"
        port = args.port or int(os.environ.get("PORT", "8080"))
    else:
        host = args.host or cfg["server"]["host"]
        port = args.port or cfg["server"]["port"]

    if mode == "local":
        candidate_yaml_path = str(Path(__file__).parent / "candidate.yaml")
        candidate_context = build_candidate_context(candidate_yaml_path)
        init_db(cfg["paths"]["db_path"])
        seed_answer_bank(cfg["paths"]["db_path"], candidate_context)
        threading.Timer(1.2, _open_browser, args=(f"http://{host}:{port}",)).start()
        _log.info(
            "Candidate       -> %s (%s, %d experience block(s))",
            candidate_context.get("personal", {}).get("name") or "unknown",
            candidate_context.get("candidate_source") or "unknown",
            len(candidate_context.get("experiences", [])),
        )
    else:
        _log.info("Mode            -> saas (Postgres + Supabase Storage)")

    _log.info("Customy running -> http://%s:%s", host, port)
    if mode == "local":
        _log.info("Database        -> %s", cfg["paths"]["db_path"])
        _log.info("Artifacts       -> %s", cfg["paths"]["applications_dir"])

    run_server(host, port, cfg)


if __name__ == "__main__":
    main()
