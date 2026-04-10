# Customy

Local-only resume tailoring app. One pasted JD in, tailored LaTeX resume + optional outputs out.

## Repo Skeleton

- `main.py` — entrypoint: config load, DB init, server boot
- `config.py` — loads config.yaml and .env
- `app/server.py` — stdlib HTTP server, JSON API, static serving
- `app/analyzer.py` — non-LLM JD analysis (role, language, keywords, scoring)
- `app/generator.py` — LLM prompt contract, normalization, safety fallbacks
- `app/latex.py` — one-page LaTeX rendering and PDF compilation
- `app/storage.py` — artifact folder creation and file writes
- `app/db.py` — SQLite persistence and dashboard stats
- `app/targeting.py` — skill inventory, keyword targeting, role normalization
- `app/models.py` — TailoredExperience and ApplicationPack dataclasses
- `app/openai_usage.py` — token tracking and cost calculation
- `prompts/system.md` — tailoring contract for the LLM

## Slash Commands

- `/generate` — full tailoring pipeline
- `/fix-latex` — fix compilation errors
- `/review-output` — audit the last generation
- `/db-check` — inspect SQLite state

## Local Overrides

- `CLAUDE.local.md` is machine-specific and must stay gitignored.
