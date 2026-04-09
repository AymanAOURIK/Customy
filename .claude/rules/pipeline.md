# Pipeline Rules

- Run `app/analyzer.py` before any LLM call.
- The analyzer owns role, language, and keyword extraction.
- The LLM handles text tailoring only, never extraction or routing.
- Keep LLM payloads compact and structured.
- Tailor via title, summary, experience phrasing and order, and skill prioritization.
- Match resume language to the JD language for English and French.
- Prefer source fixes over one-off patches.
