from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.db import application_slug_exists
from app.models import ApplicationPack

_APPLICATIONS_DIR: Path | None = None


def _name_to_filename(name: str, suffix: str) -> str:
    """Turn 'Ayman Aourik' into 'Ayman_Aourik_<suffix>'."""
    slug = re.sub(r"\s+", "_", name.strip()) or "Candidate"
    return f"{slug}_{suffix}"


def set_applications_dir(path: str) -> None:
    global _APPLICATIONS_DIR
    _APPLICATIONS_DIR = Path(path).resolve()


def _configured_applications_dir() -> Path:
    if _APPLICATIONS_DIR is None:
        raise RuntimeError("Applications directory is not configured.")
    return _APPLICATIONS_DIR


def _slugify_text(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


def make_slug(
    company: str,
    role: str,
    db_path: str | None = None,
    slug_exists_fn=None,
) -> str:
    """
    "Acme Corp" + "Data Engineer" -> "acme-corp-data-engineer-20240601"
    URL-safe, lowercase, hyphens only.
    If the configured output folder or database slug already exists, append -2, -3, etc.

    slug_exists_fn: optional callable(slug: str) -> bool for external slug checks
                    (e.g. Postgres in SaaS mode). Takes precedence alongside db_path.
    """

    applications_dir = _configured_applications_dir()
    company_slug = _slugify_text(company or "unknown-company")
    role_slug = _slugify_text(role or "untitled-role")
    dated_slug = f"{company_slug}-{role_slug}-{datetime.now().strftime('%Y%m%d')}"
    candidate = dated_slug
    index = 2
    while (
        (applications_dir / candidate).exists()
        or (db_path and application_slug_exists(db_path, candidate))
        or (slug_exists_fn and slug_exists_fn(candidate))
    ):
        candidate = f"{dated_slug}-{index}"
        index += 1
    return candidate


def write_pack(
    applications_dir: str,
    slug: str,
    jd_text: str,
    application_url: str | None,
    pack: ApplicationPack,
    tex_string: str,
    requested_outputs: list[str],
    candidate_name: str = "Candidate",
    usage_summary: dict | None = None,
    initial_analysis: dict | None = None,
    updated_analysis: dict | None = None,
) -> dict:
    """
    Creates <configured applications_dir>/<slug>/
    Always writes: job_description.md, resume.tex, generated.json
    Conditionally writes: <Name>_Cover_letter.txt, linkedin_message.md, email_draft.md
    Returns dict of all written absolute file paths.
    """

    base_dir = Path(applications_dir).resolve()
    output_dir = base_dir / slug
    output_dir.mkdir(parents=True, exist_ok=False)

    files = {
        "output_dir": str(output_dir),
        "job_description": str(output_dir / "job_description.md"),
        "resume_tex": str(output_dir / "resume.tex"),
        "generated_json": str(output_dir / "generated.json"),
    }

    (output_dir / "job_description.md").write_text(jd_text.strip() + "\n", encoding="utf-8")
    (output_dir / "resume.tex").write_text(tex_string, encoding="utf-8")
    (output_dir / "generated.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "requested_outputs": requested_outputs,
                "job_application_url": application_url or None,
                "scores": {
                    "initial_score": (initial_analysis or {}).get("score"),
                    "updated_score": (updated_analysis or {}).get("score"),
                },
                "initial_analysis": initial_analysis or {},
                "updated_analysis": updated_analysis or {},
                "usage": usage_summary or {},
                "pack": pack.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if "cover_letter" in requested_outputs and pack.cover_letter:
        cl_filename = _name_to_filename(candidate_name, "Cover_letter.txt")
        path = output_dir / cl_filename
        path.write_text(pack.cover_letter.strip() + "\n", encoding="utf-8")
        files["cover_letter"] = str(path)
        files["cover_letter_filename"] = cl_filename

    if "linkedin_msg" in requested_outputs and pack.linkedin_message:
        path = output_dir / "linkedin_message.md"
        path.write_text(pack.linkedin_message.strip() + "\n", encoding="utf-8")
        files["linkedin_message"] = str(path)

    if "email_draft" in requested_outputs and pack.email_draft:
        path = output_dir / "email_draft.md"
        path.write_text(pack.email_draft.strip() + "\n", encoding="utf-8")
        files["email_draft"] = str(path)

    return files
