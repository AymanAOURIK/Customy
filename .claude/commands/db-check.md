# /db-check

Inspect the current SQLite state.

Show:

- Last 5 generation records (`slug`, `timestamp`, `PDF status`, `language`)
- Total generation count
- Any records missing `resume.tex` confirmation
- Any duplicate slugs

Use `app/db.py`; do not run raw SQL directly against the DB file.
