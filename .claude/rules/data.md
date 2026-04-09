# Data Rules

- `candidate.yaml` is the only runtime source of truth for candidate data.
- Never write `candidate.yaml` or `config.yaml`.
- Query or write SQLite through `app/db.py`.
- Do not use previously generated application folders as model input.
- Never reintroduce runtime merging from `Original_Resumé.pdf`.
- Use `docs/tailoring_style_guide.md` as tone guidance only, never as source content to copy.
