# Agent And Claude Instruction Summary

This file consolidates the behavior and constraints currently defined in:

- `agent.md`
- `CLAUDE.md`

It is meant to be reusable as:

- a transfer brief for another directory
- a cleanup reference before tightening these instructions
- a single place to compare overlap and gaps

## Core Product Definition

The repo is `Customy`, a standalone local resume tailoring app.

Primary input:

- one pasted job description

Primary outputs:

- tailored LaTeX resume
- optional cover letter
- optional LinkedIn message
- optional email draft
- SQLite-backed history and funnel tracking

Useful work is defined as changes that improve:

- tailoring quality
- token efficiency
- local reliability
- SQLite tracking quality
- dashboard usefulness
- generation correctness
- runtime simplicity
- file output consistency
- dashboard visibility
- error handling without extra dependency weight
- fidelity to the candidate source of truth

## Shared Rules Across Both Files

These are the strongest shared instructions because both files reinforce them:

- Keep the app local-first and local-only.
- Bind services to `127.0.0.1`.
- Keep all files on disk locally.
- Do not add hosted services or remote orchestration.
- Use `candidate.yaml` as the runtime source of truth for candidate data.
- Run the pure-Python or non-LLM job-description analyzer before any LLM call.
- Keep the LLM focused on compact, structured tailoring work.
- Keep LLM payloads compact and structured.
- Preserve the standalone layout and avoid coupling this app to other repos.

## Data And Source-Of-Truth Rules

- Query or write SQLite through `app/db.py`.
- Treat `candidate.yaml` as the only runtime candidate source of truth.
- Treat the whole candidate profile as usable evidence, not only the explicit `skills:` block.
- Do not use previously generated application folders as model input.
- Never reintroduce runtime merging from `Original_Resumé.pdf`.
- Use `docs/tailoring_style_guide.md` as tone guidance only, never as source content to copy.

## Generation Pipeline Rules

- Use `app/analyzer.py` before the LLM.
- Keep the LLM focused on text tailoring only, not extraction or routing.
- Tailor by title, summary, experience phrasing and order, and skill prioritization.
- Match resume language to the job description language for English and French.
- Prefer source fixes over one-off patches.

## Output And Persistence Rules

- Always write `resume.tex`.
- `resume.pdf` is optional when `pdflatex` is missing.
- Record every successful generation in SQLite, even when PDF compilation fails.
- Generated artifacts belong in `/mnt/c/Users/LENOVO/desktop/Customy output job applications/<slug>/`.

## Quality Guardrails

- Keep the resume on one page.
- Do not invent new layout systems.
- Do not hallucinate skills, metrics, dates, companies, roles, or outcomes.

## Architectural Constraints

- No Flask, FastAPI, Django, or other web frameworks.
- No Pydantic.
- No hosted infrastructure.
- No cloud storage.
- No authentication layer.
- No external frontend libraries.

## Repo Map Captured In The Notes

Detailed file ownership from `agent.md`:

- `main.py`: local entrypoint, config load, DB init, server boot
- `config.py`: config and candidate loading
- `config.yaml`: local paths, model settings, server config
- `candidate.yaml`: canonical runtime candidate profile and evidence base
- `app/server.py`: HTTP API, generation orchestration, artifact serving
- `app/analyzer.py`: non-LLM JD analysis, role, language, and keyword extraction
- `app/generator.py`: LLM prompt contract, normalization, safety fallbacks
- `app/latex.py`: one-page resume rendering and PDF compilation
- `app/storage.py`: artifact folder creation and writes
- `app/db.py`: SQLite persistence and dashboard stats
- `prompts/system.md`: tailoring contract for the LLM
- `docs/tailoring_style_guide.md`: canonical tone and structure reference

Important paths called out by `CLAUDE.md`:

- `main.py`
- `config.yaml`
- `candidate.yaml`
- `app/`
- `prompts/`
- `resume/`
- `applications/`

## Differences And Tensions Worth Cleaning Up

- Output location is not expressed the same way in both files.
- `agent.md` points to `/mnt/c/Users/LENOVO/desktop/Customy output job applications/<slug>/`.
- `CLAUDE.md` highlights `applications/` as an important repo path.
- If you want a cleaner transfer prompt, unify artifact-path wording into one exact rule.

## Portable Instruction Block

Use this when seeding another directory with the same behavior:

```md
This project is a standalone local resume tailoring app.

Purpose:
- improve tailoring quality
- improve token efficiency
- improve local reliability
- improve SQLite tracking and dashboard usefulness

Operating rules:
- keep the app local-only and bind to 127.0.0.1
- keep files on disk locally only
- do not add hosted services, cloud storage, or remote orchestration
- preserve repo independence and do not couple it to other repos

Data rules:
- use candidate.yaml as the only runtime source of truth for candidate data
- use app/db.py for SQLite reads and writes
- do not use generated application folders as model input
- do not reintroduce runtime merging from Original_Resume.pdf
- use docs/tailoring_style_guide.md only for tone guidance, never as source content

Pipeline rules:
- run the non-LLM job-description analyzer before any LLM call
- keep the analyzer responsible for extraction and routing signals
- keep the LLM focused on compact, structured text tailoring only
- prefer source fixes over one-off patches

Quality rules:
- keep the resume to one page
- do not invent a new layout system
- do not hallucinate skills, metrics, dates, companies, roles, or outcomes
- tailor through title, summary, experience phrasing and order, and skill prioritization
- match output language to the job description language, including English and French

Output rules:
- always write resume.tex
- resume.pdf is optional if pdflatex is unavailable
- record successful generations in SQLite even if PDF compilation fails

Constraints:
- no Flask, FastAPI, Django, or similar frameworks
- no Pydantic
- no hosted infrastructure
- no authentication layer
- no external frontend libraries
```

## File-Origin Breakdown

Only in `agent.md`:

- token efficiency is a named optimization target
- SQLite tracking quality and dashboard usefulness are explicit product goals
- generated artifacts are assigned an absolute output path
- `Original_Resumé.pdf` must never be merged back into runtime data
- generated application folders must not be reused as model input
- `docs/tailoring_style_guide.md` is tone-only guidance
- specific module responsibilities are documented
- one-page and no-hallucination rules are explicit

Only in `CLAUDE.md`:

- the app input is explicitly one pasted job description
- optional cover letter, LinkedIn message, and email draft are explicit outputs
- every successful generation must be recorded in SQLite even if PDF compilation fails
- `resume.tex` must always be written even if `resume.pdf` cannot be built
- framework and dependency exclusions are listed explicitly
