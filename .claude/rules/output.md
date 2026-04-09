# Output Rules

- Always write `resume.tex`.
- Attempt `pdflatex`; `resume.pdf` is optional if `pdflatex` is unavailable or compilation fails.
- Log the PDF result either way.
- Record every successful generation in SQLite even when PDF compilation fails.
- Write generated artifacts to `/mnt/c/Users/LENOVO/desktop/Customy output job applications/<slug>/`.
- Report the slug path, detected language, PDF status, and SQLite row ID after generation.
