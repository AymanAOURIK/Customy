# /generate

Implement this pipeline for a pasted job description.

Steps:

1. Confirm `candidate.yaml` is loaded.
2. Run `app/analyzer.py` on the pasted JD.
3. Pass analyzer output and candidate data to `app/generator.py`.
4. Write `resume.tex` to the output slug folder.
5. Attempt `pdflatex` compilation and log the result either way.
6. Record the generation in SQLite via `app/db.py`.
7. Report the slug path, detected language, PDF status, and SQLite row ID.
