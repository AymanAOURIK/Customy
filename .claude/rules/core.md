# Core Rules

- `Customy` is a standalone local resume tailoring app.
- Input is one pasted job description.
- Outputs can include a tailored LaTeX resume, optional cover letter, optional LinkedIn message, optional email draft, and SQLite-backed history and funnel tracking.
- Keep the app local-only and bound to `127.0.0.1`.
- Preserve the standalone layout and avoid coupling this app to other repos.
- No Flask, FastAPI, Django, or other web frameworks.
- No Pydantic.
- No hosted infrastructure, cloud storage, or authentication layer.
- No external frontend libraries.
- No new dependencies without explicit approval.
