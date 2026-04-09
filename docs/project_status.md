# Project Status

## What Exists And Works

Customy currently works as a local resume-tailoring pipeline:

1. `main.py` loads config, initializes SQLite, builds candidate context, and starts the local server.
2. `app/server.py` accepts a pasted JD, rebuilds candidate context from `candidate.yaml`, runs analysis, calls generation, renders LaTeX, attempts PDF compilation, writes artifacts to the configured external output folder, and records the run in SQLite.
3. `app/analyzer.py` extracts company, role, language, location, keyword signals, matched candidate keywords, missing keywords, top requirements, and a JD-coverage fit score before any LLM call.
4. `app/generator.py` sends a compact payload to the LLM, normalizes the response, repairs weak outputs, and falls back to deterministic content when needed.
5. `app/targeting.py` now holds the shared keyword catalog, role-target lists, title normalization logic, evidence-backed skill derivation, and JD-prioritized skill selection logic used across the pipeline.
6. `app/models.py` validates the generated pack structure.
7. `app/latex.py` renders the one-page LaTeX resume, computes inclusive month durations, and attempts `pdflatex`.
8. `app/storage.py` writes `job_description.md`, `resume.tex`, `generated.json`, and any optional outputs into `/mnt/c/Users/LENOVO/desktop/Customy output job applications/<slug>/`.
9. `app/db.py` persists generation rows, dashboard stats, API usage, duplicate flags, and read-only generation-analysis helpers that combine SQLite rows with `generated.json`.
10. `app/profile.py`, `app/openai_usage.py`, `app/pdf_import.py`, and `app/resume_source.py` support candidate shaping, usage tracking, and resume-source ingestion outside the main request path.

What is already solid:

- The app is local-only and artifact output already lives outside the repo.
- `candidate.yaml` remains the runtime source of truth.
- Each generation writes `resume.tex` and stores artifact metadata in SQLite.
- The dashboard reads application history and score fields from SQLite and now lets the user manually flag duplicates without deleting history.
- Duplicate rows remain visible in history but are excluded from funnel, daily activity, and application-count stats.
- Generated artifact folders contain enough data to audit initial vs updated analysis after the fact.

## Current Tailoring Logic

The current tailoring flow is:

1. Analyze the JD first with `app/analyzer.py`.
2. Build candidate keywords from the whole candidate profile, not only the handwritten `skills:` block.
3. Build a JD-to-evidence bridge layer so supported underlying concepts can be inferred from verified profile evidence.
4. Map the strongest JD requirements to the strongest supported candidate bullets.
5. Let the LLM tailor wording, bullet order, and emphasis.
6. Normalize the result deterministically before rendering.

This means:

- The JD drives what gets emphasized.
- The candidate profile still decides what is allowed.
- Skills are no longer selected only from the explicit `skills:` section.
- Skills can now be surfaced if they are evidenced anywhere in `candidate.yaml`, including experience bullets and other verified profile text.
- When the JD asks for a more specific concept than the profile states literally, the pipeline can surface the closest supported underlying capability instead of dropping the match entirely.
- Unsupported JD terms still stay out of the final resume.

## Resume Rules Now Enforced In Code

- The resume remains one page.
- The summary is compact and currently enforced as 2 to 3 sentences.
- Graduation project, internship, trainee, and equivalent end-of-study professional entries must be kept when present in the candidate profile.
- Experience blocks stay in reverse chronological order.
- Bullet counts are preserved per experience.
- Skills are selected by JD relevance from the candidate's evidence-backed skill inventory.
- The summary can inject JD-relevant derived concepts when they are supported by experience evidence.
- Soft skills remain secondary to hard, JD-relevant proof.

## ATS-Oriented Behavior

The current implementation is intentionally ATS-friendly:

- standard section headings
- reverse chronological experience
- dense but factual phrasing
- no invented metrics, dates, or stack terms
- strongest JD-relevant proof first
- keyword exposure through real bullets, not only the skills section

The guiding rule is: the skills section is an index, but the real proof must still exist in the experience evidence.

## Recent Changes Reflected In The Current State

- The analyzer is better at LinkedIn-style JD cleanup and now extracts cleaner company names and richer requirement signals.
- `top_requirements` is now populated more reliably on structured French JDs that use emoji or decorative headings.
- Skills are now derived from candidate evidence across the full profile, then prioritized against the JD.
- The generator no longer drops substantive older experience blocks such as graduation projects.
- Duration rendering now uses inclusive month counting, which fixes undercounted ongoing roles.
- The LaTeX renderer and summary guardrails were tightened so restored experience blocks can still fit on one page.
- The dashboard now supports manual duplicate marking, and duplicate rows no longer skew generated or applied counts.

## Known Limits

The current system is better structured, but these limits still exist:

- The fit score is now a weighted JD-coverage heuristic, not a calibrated hiring-likelihood model.
- Cross-language aliasing is still shallow. English and French equivalents can still split match and missing signals.
- A true skill that is missing everywhere in `candidate.yaml` still cannot be surfaced safely.
- Duplicate handling is manual today; automatic URL and fuzzy duplicate detection is still not implemented.
- The skills inventory can only be as good as the source evidence stored in the candidate profile.

## Recommended Operating Model

The right mental model for the app is:

- `candidate.yaml` is the verified fact base.
- The analyzer determines what the JD is asking for.
- The generator decides how to present the best supported proof.
- The skills section should mirror the JD only through evidence already present in the candidate source.

This keeps the app truthful while making customization sharper and more ATS-effective.

## What Still Needs To Be Built

- Better cross-language and alias matching for terms that currently fragment the score.
- Automatic duplicate detection through URL and fuzzy title plus company matching.
- Tests around score behavior, skill derivation, duplicate exclusion, and one-page rendering.
- A cleaner review workflow for profile gaps that are true but not yet captured anywhere in `candidate.yaml`.
