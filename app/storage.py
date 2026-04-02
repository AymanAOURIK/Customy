from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.models import ApplicationPack

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_APPLICATIONS_DIR = PROJECT_ROOT / "applications"
COVER_LETTER_FILENAME = "Ayman_Aourik_Cover_letter.txt"


def set_applications_dir(path: str) -> None:
    global _APPLICATIONS_DIR
    _APPLICATIONS_DIR = Path(path).resolve()


def _slugify_text(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


def make_slug(company: str, role: str) -> str:
    """
    "Acme Corp" + "Data Engineer" -> "acme-corp-data-engineer-20240601"
    URL-safe, lowercase, hyphens only.
    If applications/<slug>/ exists, append -2, -3, etc.
    """

    company_slug = _slugify_text(company or "unknown-company")
    role_slug = _slugify_text(role or "untitled-role")
    dated_slug = f"{company_slug}-{role_slug}-{datetime.now().strftime('%Y%m%d')}"
    candidate = dated_slug
    index = 2
    while (_APPLICATIONS_DIR / candidate).exists():
        candidate = f"{dated_slug}-{index}"
        index += 1
    return candidate


def write_pack(
    applications_dir: str,
    slug: str,
    jd_text: str,
    pack: ApplicationPack,
    tex_string: str,
    requested_outputs: list[str],
    usage_summary: dict | None = None,
) -> dict:
    """
    Creates applications/<slug>/
    Always writes: job_description.md, resume.tex, generated.json
    Conditionally writes: Ayman_Aourik_Cover_letter.txt, linkedin_message.md, email_draft.md
    Returns dict of all written absolute file paths.
    """

    base_dir = Path(applications_dir).resolve()
    output_dir = base_dir / slug
    output_dir.mkdir(parents=True, exist_ok=True)

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
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "requested_outputs": requested_outputs,
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
        path = output_dir / COVER_LETTER_FILENAME
        path.write_text(pack.cover_letter.strip() + "\n", encoding="utf-8")
        files["cover_letter"] = str(path)

    if "linkedin_msg" in requested_outputs and pack.linkedin_message:
        path = output_dir / "linkedin_message.md"
        path.write_text(pack.linkedin_message.strip() + "\n", encoding="utf-8")
        files["linkedin_message"] = str(path)

    if "email_draft" in requested_outputs and pack.email_draft:
        path = output_dir / "email_draft.md"
        path.write_text(pack.email_draft.strip() + "\n", encoding="utf-8")
        files["email_draft"] = str(path)

    return files
