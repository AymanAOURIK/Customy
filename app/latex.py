from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from app.models import ApplicationPack


_METRIC_PATTERN = re.compile(
    r"(?<!\w)(?:~?\$?\d[\d,]*(?:\.\d+)?(?:[KMBkmb])?\+?(?:%|x)?(?:/[A-Za-z]+)?(?:\s?(?:hours/week|calls/week|leads/month|agents|engineers|months|years|calls|hours))?)(?!\w)"
)


def _escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    normalized = (
        str(text or "")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    return "".join(replacements.get(char, char) for char in normalized)


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
            continue
        merged.append((start, end))
    return merged


def _latex_with_metrics(text: str) -> str:
    raw = str(text or "")
    spans = [match.span() for match in _METRIC_PATTERN.finditer(raw)]
    spans = _merge_spans(spans)
    if not spans:
        return _escape(raw)

    parts = []
    cursor = 0
    for start, end in spans:
        if cursor < start:
            parts.append(_escape(raw[cursor:start]))
        parts.append(r"\textbf{" + _escape(raw[start:end]) + "}")
        cursor = end
    if cursor < len(raw):
        parts.append(_escape(raw[cursor:]))
    return "".join(parts)


def _ensure_period(text: str) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        return ""
    if cleaned[-1] in ".!?":
        return cleaned
    return cleaned + "."


def _format_resume_date(value: str, resume_language: str = "en") -> str:
    cleaned = " ".join(str(value or "").strip().split())
    if not cleaned:
        return ""
    if cleaned.lower() == "present":
        return "Présent" if resume_language == "fr" else "Present"
    if re.fullmatch(r"\d{4}-\d{2}", cleaned):
        return cleaned.replace("-", "/")
    return cleaned


def _format_period(start: str, end: str, resume_language: str = "en") -> str:
    left = _format_resume_date(start, resume_language)
    right = _format_resume_date(end, resume_language)
    if left and right:
        return f"{left} -- {right}"
    return left or right


def _parse_year_month(value: str) -> tuple[int, int] | None:
    cleaned = " ".join(str(value or "").strip().split())
    match = re.fullmatch(r"(\d{4})-(\d{2})", cleaned)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _duration_from_dates(start: str, end: str, resume_language: str = "en") -> str:
    start_parts = _parse_year_month(start)
    if not start_parts:
        return ""
    if str(end).strip().lower() == "present":
        end_parts = (date.today().year, date.today().month)
    else:
        end_parts = _parse_year_month(end)
    if not end_parts:
        return ""

    # Resume dates are month-precision only, so count both boundary months.
    months = ((end_parts[0] - start_parts[0]) * 12 + (end_parts[1] - start_parts[1])) + 1
    if months <= 0:
        return ""
    years, remainder = divmod(months, 12)
    if years and remainder:
        if resume_language == "fr":
            year_label = "an" if years == 1 else "ans"
            month_label = "mois"
            return f"{years} {year_label} et {remainder} {month_label}"
        year_label = "year" if years == 1 else "years"
        month_label = "month" if remainder == 1 else "months"
        return f"{years} {year_label} and {remainder} {month_label}"
    if years:
        if resume_language == "fr":
            year_label = "an" if years == 1 else "ans"
            return f"{years} {year_label}"
        year_label = "year" if years == 1 else "years"
        return f"{years} {year_label}"
    month_label = "mois" if resume_language == "fr" else ("month" if months == 1 else "months")
    return f"{months} {month_label}"


def _experience_meta(candidate: dict, role: str, company: str) -> dict:
    for item in candidate.get("experiences", []):
        if str(item.get("role", "")).strip() == role and str(item.get("company", "")).strip() == company:
            return item
    return {}


def _render_contact_row(left: str, right: str) -> str:
    return f"{left} & {right} \\\\"


def _join_skill_items(items: list[str]) -> str:
    return " $\\cdot$ ".join(_escape(item) for item in items if str(item).strip())


def _skill_columns(candidate: dict, tailored: ApplicationPack) -> tuple[str, str]:
    tailored_hard = []
    for field in ("languages", "frameworks", "tools"):
        tailored_hard.extend(list(tailored.tailored_skills.get(field, [])))

    technical = []
    seen = set()
    for item in tailored_hard:
        cleaned = " ".join(str(item or "").strip().split())
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        technical.append(cleaned)
        seen.add(key)

    soft_items = []
    seen_soft = set()
    for item in list(candidate.get("skills", {}).get("soft", [])):
        cleaned = " ".join(str(item or "").strip().split())
        key = cleaned.lower()
        if not cleaned or key in seen_soft:
            continue
        soft_items.append(cleaned)
        seen_soft.add(key)

    return _join_skill_items(technical), _join_skill_items(soft_items)


def _education_period(item: dict) -> str:
    start_year = item.get("start_year")
    end_year = item.get("end_year") or item.get("year")
    if start_year and end_year:
        return f"{start_year} -- {end_year}"
    if end_year:
        return str(end_year)
    return ""


def _localize_spoken_language(value: str, resume_language: str) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    if resume_language != "fr":
        return cleaned
    mapping = {
        "English (Fluent)": "Anglais (Courant)",
        "French (Fluent)": "Français (Courant)",
        "Arabic (Native)": "Arabe (Natif)",
    }
    return mapping.get(cleaned, cleaned)


def _language_table(spoken_languages: list[str], resume_language: str) -> list[str]:
    if not spoken_languages:
        return []
    cells = " ".join("X" for _ in spoken_languages)
    row = " & ".join(f"$\\bullet$ {_escape(_localize_spoken_language(item, resume_language))}" for item in spoken_languages)
    return [
        "\\resheading{Langues}" if resume_language == "fr" else "\\resheading{Languages}",
        f"\\begin{{tabularx}}{{\\textwidth}}{{@{{}}{cells}@{{}}}}",
        row + r"\\",
        "\\end{tabularx}",
    ]


def render_tex(candidate: dict, tailored: ApplicationPack, jd_analysis: dict | None = None) -> str:
    personal = candidate.get("personal", {})
    education = candidate.get("education", [])
    spoken_languages = list(candidate.get("spoken_languages", []))
    resume_language = getattr(tailored, "resume_language", "en") or "en"
    technical_col, soft_col = _skill_columns(candidate, tailored)

    job_blocks = []
    for item in tailored.tailored_experiences:
        meta = _experience_meta(candidate, item.role, item.company)
        period = _format_period(item.start, item.end, resume_language)
        location = _escape(meta.get("location", ""))
        duration = str(meta.get("duration", "") or "").strip() or _duration_from_dates(item.start, item.end, resume_language)
        title_line = f"{_escape(item.role)}: {_escape(item.company)}"
        job_blocks.extend(
            [
                rf"\resjob{{{_escape(period)}}}{{{location}}}{{{title_line}}}{{{_escape(duration)}}}{{",
                r"\begin{itemize}",
            ]
        )
        for bullet in item.bullets:
            job_blocks.append(f"  \\item {_latex_with_metrics(_ensure_period(bullet))}")
        job_blocks.extend([r"\end{itemize}", "}"])

    education_blocks = []
    for item in education:
        degree = str(item.get("degree", "")).strip()
        institution = str(item.get("institution", "")).strip()
        details = institution
        education_blocks.append(
            rf"\resedu{{{_escape(_education_period(item))}}}{{{_escape(', '.join(part for part in [degree, institution] if part))}}}{{{_escape(str(item.get('details', '')))}}}"
        )
        if not degree and details:
            education_blocks[-1] = rf"\resedu{{{_escape(_education_period(item))}}}{{{_escape(details)}}}{{}}"

    contact_rows = [
        _render_contact_row(
            rf"\Letter\ \href{{mailto:{_escape(personal.get('email', ''))}}}{{{_escape(personal.get('email', ''))}}}" if personal.get("email") else "",
            rf"\phone\ {_escape(personal.get('phone', ''))}" if personal.get("phone") else "",
        ),
        _render_contact_row(
            _escape(personal.get("location", "")),
            rf"\href{{https://www.linkedin.com/{_escape(personal.get('linkedin', '').lstrip('/'))}}}{{{_escape(personal.get('linkedin', ''))}}}" if personal.get("linkedin") else _escape(personal.get("github", "")),
        ),
    ]

    language_section = _language_table(spoken_languages, resume_language)

    return "\n".join(
        [
            r"\documentclass[8pt,a4paper]{extarticle}",
            r"\usepackage[margin=0.34in]{geometry}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{lmodern}",
            r"\usepackage[hidelinks]{hyperref}",
            r"\usepackage{enumitem}",
            r"\usepackage{titlesec}",
            r"\usepackage{tabularx}",
            r"\usepackage{wasysym}",
            r"\pagestyle{empty}",
            r"\flushbottom",
            r"\setlength{\parindent}{0pt}",
            r"\setlength{\parskip}{0.35pt plus 0.35pt minus 0.15pt}",
            r"\titleformat{\section}{\normalsize\bfseries}{}{0em}{}[\titlerule]",
            r"\titlespacing*{\section}{0pt}{2.5pt plus 0.8pt minus 0.4pt}{1.2pt plus 0.4pt minus 0.2pt}",
            r"\setlist[itemize]{leftmargin=1.0em,itemsep=0pt,topsep=0pt,parsep=0pt,partopsep=0pt}",
            "",
            r"\newcommand{\resheading}[1]{\section*{#1}}",
            r"\newcommand{\resjob}[5]{",
            r"\noindent\begin{tabularx}{\textwidth}{@{}p{0.19\textwidth}@{\hspace{0.03\textwidth}}X@{}}",
            r"\raggedright #1\\#2 &",
            r"\textbf{#3} (#4)\\",
            r"& #5",
            r"\end{tabularx}\vspace{0pt}",
            r"}",
            r"\newcommand{\resedu}[3]{",
            r"\noindent\begin{tabularx}{\textwidth}{@{}p{0.19\textwidth}@{\hspace{0.03\textwidth}}X@{}}",
            r"\raggedright #1 & \textbf{#2}\\",
            r"& #3",
            r"\end{tabularx}\vspace{0pt}",
            r"}",
            "",
            r"\begin{document}",
            "",
            rf"{{\Large \textbf{{{_escape(personal.get('name', ''))}}} \ \textit{{{_escape(tailored.tailored_title)}}}}}\\[2pt]",
            r"\begin{tabularx}{\textwidth}{@{}X X@{}}",
            *contact_rows,
            r"\end{tabularx}",
            "",
            r"\resheading{Résumé}" if resume_language == "fr" else r"\resheading{Summary}",
            _latex_with_metrics(_ensure_period(tailored.tailored_summary)),
            "",
            r"\resheading{Expérience}" if resume_language == "fr" else r"\resheading{Work Experience}",
            *job_blocks,
            "",
            r"\resheading{Formation}" if resume_language == "fr" else r"\resheading{Education}",
            *education_blocks,
            "",
            r"\resheading{Compétences}" if resume_language == "fr" else r"\resheading{Skills}",
            r"\begin{tabularx}{\textwidth}{@{}X X@{}}",
            f"{technical_col} & {soft_col} \\\\",
            r"\end{tabularx}",
            "",
            *language_section,
            "",
            r"\end{document}",
            "",
        ]
    )


def compile_pdf(tex_path: str, output_dir: str, output_filename: str | None = None) -> str | None:
    if shutil.which("pdflatex") is None:
        return None

    tex_file = Path(tex_path).resolve()
    out_dir = Path(output_dir).resolve()
    try:
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                f"-output-directory={out_dir}",
                str(tex_file),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception as exc:
        print(f"pdflatex execution failed: {exc}", file=sys.stderr)
        return None

    pdf_path = out_dir / f"{tex_file.stem}.pdf"
    if result.returncode != 0 or not pdf_path.exists():
        combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        if combined:
            print(combined, file=sys.stderr)
        return None

    if output_filename:
        target_path = out_dir / output_filename
        if target_path != pdf_path:
            if target_path.exists():
                target_path.unlink()
            pdf_path = pdf_path.replace(target_path)

    return str(pdf_path)
