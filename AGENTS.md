# Codex Agent Notes

## Operating Model

`Customy` is a single-purpose local application. Work should improve one of:

- tailoring quality
- token efficiency
- local reliability
- SQLite tracking quality
- dashboard usefulness

## Decision Rules

- Query or write SQLite through `app/db.py`.
- Use `app/analyzer.py` before the LLM.
- Keep LLM payloads compact and structured.
- Treat `candidate.yaml` as the only runtime candidate source of truth.
- Generated artifacts belong in `/mnt/c/Users/LENOVO/desktop/Customy output job applications/<slug>/`.
- Preserve the standalone layout and avoid coupling this app to other repos.
- Never reintroduce runtime merging from `Original_Resumé.pdf`.
- Do not use previously generated application folders as model input.
- Use `docs/tailoring_style_guide.md` as tone guidance only, never as source content to copy.

## Repo Skeleton

- `main.py`: local entrypoint, config load, DB init, server boot.
- `config.py`: config and candidate loading.
- `config.yaml`: local paths, model settings, server config.
- `candidate.yaml`: canonical runtime candidate profile and skills inventory.
- `app/server.py`: HTTP API, generation orchestration, artifact serving.
- `app/analyzer.py`: non-LLM JD analysis, role/language/keyword extraction.
- `app/generator.py`: LLM prompt contract, normalization, safety fallbacks.
- `app/latex.py`: one-page resume rendering and PDF compilation.
- `app/storage.py`: artifact folder creation and writes.
- `app/db.py`: SQLite persistence and dashboard stats.
- `prompts/system.md`: tailoring contract for the LLM.
- `docs/tailoring_style_guide.md`: canonical tone and structure reference.

## Quality Guardrails

- Keep the resume on one page.
- Do not invent new layout systems.
- Do not hallucinate skills, metrics, dates, companies, roles, or outcomes.
- Tailor by title, summary, experience phrasing/order, and skill prioritization.
- Match resume language to JD language for English and French.
- Prefer source fixes over one-off patches.

## Local-Only Constraint

- Bind to `127.0.0.1`
- Keep all files on disk locally
- Do not add remote orchestration or hosted services

## Definition Of Useful Work

A change is useful when it improves:

- generation correctness
- runtime simplicity
- file output consistency
- dashboard visibility
- error handling without extra dependency weight
- fidelity to the candidate source of truth
