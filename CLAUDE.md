# Claude Operating Notes

## Repo Purpose

This repo is `Customy`, a standalone local resume tailoring app.

Input:
- one pasted job description

Outputs:
- tailored LaTeX resume
- optional cover letter
- optional LinkedIn message
- optional email draft
- SQLite-backed history and funnel tracking

## Working Rules

- Keep the app local-first and bound to `127.0.0.1` only.
- Use `candidate.yaml` as the runtime source of truth for candidate data.
- Run the pure-Python JD analyzer before any LLM call.
- Keep the LLM focused on text tailoring only, not extraction or routing.
- Record every successful generation in SQLite, even when PDF compilation fails.
- Always write `resume.tex`; `resume.pdf` is optional when `pdflatex` is missing.

## Important Paths

- `main.py`
- `config.yaml`
- `candidate.yaml`
- `app/`
- `prompts/`
- `resume/`
- `applications/`

## Constraints

- No Flask, FastAPI, Django, or other web frameworks
- No Pydantic
- No hosted infrastructure
- No cloud storage
- No authentication layer
- No external frontend libraries
