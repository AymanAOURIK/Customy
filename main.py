#!/usr/bin/env python3
"""Customy - Local resume tailor. Usage: python main.py [--port 8765] [--host 127.0.0.1]"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import threading
import webbrowser
from pathlib import Path

from app.db import init_db
from app.profile import build_candidate_context
from app.server import run_server
from config import load_config


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
    host = args.host or cfg["server"]["host"]
    port = args.port or cfg["server"]["port"]

    candidate_yaml_path = str(Path(__file__).parent / "candidate.yaml")
    candidate_context = build_candidate_context(candidate_yaml_path)

    init_db(cfg["paths"]["db_path"])

    threading.Timer(1.2, _open_browser, args=(f"http://{host}:{port}",)).start()

    print(f"\n  Customy running -> http://{host}:{port}")
    print(f"  Database        -> {cfg['paths']['db_path']}")
    print(f"  Artifacts       -> {cfg['paths']['applications_dir']}\n")
    print(
        "  Candidate       -> "
        f"{candidate_context.get('personal', {}).get('name') or 'unknown'} "
        f"({candidate_context.get('candidate_source') or 'unknown'}, "
        f"{len(candidate_context.get('experiences', []))} experience block(s))\n"
    )

    run_server(host, port, cfg)


if __name__ == "__main__":
    main()
