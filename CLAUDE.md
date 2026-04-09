# Customy Agent Notes

## Hard Rules

- local-only, bind `127.0.0.1`
- no Flask, FastAPI, Django, Pydantic, cloud, auth, or external frontend libraries
- no new dependencies without explicit approval
- never write `candidate.yaml` or `config.yaml`
- never hallucinate skills, metrics, dates, companies, roles, or outcomes
- prefer source fixes over one-off patches

## Pipeline Order

1. `app/analyzer.py` first: extract role, language, and keywords without the LLM.
2. LLM second: text tailoring only, never extraction or routing.
3. Tailor through title, summary, experience phrasing and order, and skill priority.
4. Match output language to the JD language (`EN` or `FR`).

## Output Rules

- always write `resume.tex`
- `resume.pdf` is optional when `pdflatex` is unavailable
- record every generation in SQLite even if PDF compilation fails
- artifacts go to `/mnt/c/Users/LENOVO/desktop/Customy output job applications/<slug>/`

## Rules

- `.claude/rules/core.md`
- `.claude/rules/data.md`
- `.claude/rules/pipeline.md`
- `.claude/rules/output.md`
- `.claude/rules/quality.md`

## Slash Commands

- `/generate`: full tailoring pipeline
- `/fix-latex`: fix compilation errors
- `/review-output`: audit the last generation
- `/db-check`: inspect SQLite state

## Local Overrides

- `CLAUDE.local.md` is machine-specific and must stay gitignored.
- `AGENTS.md` is a symlink to this file so Claude and Codex read one root entrypoint.
