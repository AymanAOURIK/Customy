"""Resume text extraction for Customy V3 onboarding.

Supports PDF (via pypdf, already in requirements.txt) and plain text (.txt, .md).
Returns sanitized extracted text only — no LLM, no rewriting.
"""
from __future__ import annotations

import io

from app.text_utils import sanitize_text


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract raw text from an uploaded resume file.

    Supports .pdf, .txt, and .md extensions.
    Raises ValueError on parse failure or unsupported format.
    """
    name = filename.lower()
    if name.endswith(".pdf"):
        raw_text = _extract_pdf(file_bytes)
        parse_path = "pdf"
    elif name.endswith((".txt", ".md")):
        raw_text = file_bytes.decode("utf-8", errors="replace")
        parse_path = "text"
    else:
        raise ValueError(
            f"Unsupported file type '{filename}'. Upload a .pdf, .txt, or .md file."
        )

    sanitized = sanitize_text(raw_text, preserve_newlines=True)
    if not sanitized:
        raise ValueError(
            f"Uploaded {parse_path} file contains no usable text after sanitization."
        )
    return sanitized


def _extract_pdf(file_bytes: bytes) -> str:
    try:
        import pypdf
    except ImportError as exc:
        raise ValueError(
            "PDF parsing unavailable (pypdf not installed)."
        ) from exc

    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc

    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)

    result = "\n".join(pages).strip()
    if not result:
        raise ValueError(
            "PDF contains no extractable text. "
            "Try uploading a plain-text (.txt) version of your resume."
        )
    return result
