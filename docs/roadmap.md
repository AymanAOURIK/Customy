# Customy — Corrected Roadmap

> From reliable resume tailor to auditable apply-assist, built on truthful outputs and high-signal job selection.

---

## 1. Critique of the Previous Roadmap

The prior roadmap had the right long-term vision but the wrong execution order and several structural problems:

**Wrongly prioritized:**
- Phase 1 included batch regeneration, A/B prompt comparison, generation diff view, config-driven model selection, and CSV/JSON export. These are polish features that do not fix any current quality gap. They add surface area before the core pipeline is solid.
- Phase 2 jumped straight to a URL collector UI and bulk generate before defining a job data model, a policy engine, or deduplication logic. This makes the job queue a dumb list instead of a decision system.
- Phase 3 put LinkedIn scraping, anti-detection, and multi-source scrapers as a core phase. This is high-risk, high-maintenance infrastructure that is unnecessary for months. Company career pages, ATS RSS feeds, and direct job URLs are simpler and more reliable first sources.
- Phase 4 introduced LangChain, LangGraph, and Langfuse simultaneously as prerequisites for auto-apply. None of these are needed. LangChain adds abstraction over raw OpenAI calls that are already clean. LangGraph is premature when the state machine is two steps. Langfuse is useful but it is observability, not capability.

**Missing entirely:**
- No scoring calibration model. The current score is `keyword_ratio * 60 + seniority_bonus + remote_bonus + location_bonus`. This is not predictive of fit. Weighted requirement coverage, seniority alignment, and domain match need to be scored before any ranking or auto-apply decision.
- No cross-language keyword aliasing. English JDs and French JDs fragment the score because `machine learning` and `apprentissage automatique` are separate keywords. This breaks bilingual targeting.
- No output quality gates. The generator produces a pack that is written to disk unconditionally. There is no automated check for bullet count preservation, language purity, title format, one-page fit, or factual integrity before the artifact is committed.
- No regression test suite. Zero tests exist in the repo. No test for analyzer extraction, score behavior, skill derivation, bullet preservation, or LaTeX rendering. Any change to the pipeline is a blind deployment.
- No job data model. The `applications` table tracks what was generated, not what jobs exist. There is no concept of a job that exists independently of a generated resume.
- No policy engine. There is no rule about which jobs qualify for generation, which qualify for apply, what geography rules apply, or what seniority range is acceptable. Without policy, auto-apply is uncontrolled.
- No application resources layer. There is no answer bank, no salary rules, no work authorization data, no form-answer provenance. Auto-apply without these is not possible.
- No human approval gates before Phase 4.2, which is far too late. Approval gates are a prerequisite for any apply action, not a late add-on.

**Structural problems:**
- The roadmap treated multi-user (Phase 5) as a real priority. This is a single-candidate app. Multi-user and Docker belong in a different product.
- LangChain/LangGraph were positioned as architectural prerequisites. They are optional abstractions. The current `openai` SDK calls with structured output are already compact and type-safe.
- Scraping was conflated with discovery. Discovery means knowing about jobs. Scraping is one way to discover jobs, and the riskiest one. ATS watchlists, direct URLs, and RSS feeds should come first.

---

## 2. Corrected Phased Strategy

### Phase 1 — Make Customization Reliably Strong (v1.2.x — v1.4.x)

The current pipeline works but has real quality gaps that must be fixed before any automation is safe.

| Task | Priority | Version |
|------|----------|---------|
| Regression test suite: analyzer extraction, score behavior, skill derivation, bullet count preservation, LaTeX one-page rendering | Critical | v1.2.0 |
| Evaluation samples: 5-10 saved JD+output pairs with expected scores and known extraction results for regression | Critical | v1.2.0 |
| Weighted scoring model: replace flat keyword ratio with requirement coverage weight, seniority alignment, domain-match signal, experience-years alignment | Done | v1.1.1 |
| Cross-language keyword aliasing: build a bilingual alias map (EN<->FR) so `machine learning` and `apprentissage automatique` are the same signal | High | v1.2.0 |
| Deterministic title normalization: extend `normalize_role_title` with a canonical mapping for common variants (e.g. `Data Engineer` / `Ingénieur Data` / `Data Engineering Lead` -> normalized form) | High | v1.3.0 |
| Output quality gates: automated checks before write — bullet count matches source, language purity (no mixed-language bullets), title passes `is_credible_role_title`, summary is 2-3 sentences, one-page LaTeX renders without overflow | High | v1.3.0 |
| Prompt hash tracking: store a hash of `system.md` per generation so outputs are reproducible and prompt changes are traceable | Medium | v1.3.0 |
| Stronger requirement extraction: handle more JD formats (numbered lists, inline requirements, tables) in `_extract_top_requirements` | Medium | v1.4.0 |
| Score calibration feedback: after N generations, compute average delta between initial and updated score to detect scoring drift | Medium | v1.4.0 |

**What this phase does NOT include:**
- Batch regeneration, A/B prompts, generation diff view, CSV export, config-driven model selection. These are deferred until the core is proven reliable.

### Phase 2 — Job Intake and Ranking (v2.0.x — v2.2.x)

Before auto-apply, the system needs to know about jobs independently of resume generation.

| Task | Priority | Version |
|------|----------|---------|
| `jobs` table in SQLite (see schema below) | Critical | v2.0.0 |
| Manual job intake: paste a URL + JD text, system extracts metadata and stores in `jobs` table | Critical | v2.0.0 |
| Auto-score ingested jobs against candidate profile before generation | Critical | v2.0.0 |
| Dedupe key: URL normalization + fuzzy company+title matching to prevent duplicate job entries | High | v2.0.0 |
| ATS vendor detection: identify Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters from URL patterns (already partially in `analyzer.py`) | High | v2.1.0 |
| Company watchlist: maintain a list of target companies; flag when a new job from a watched company is ingested | High | v2.1.0 |
| Job queue view in dashboard: sorted by fit score, filterable by source/location/seniority/status | Medium | v2.1.0 |
| Job expiration tracking: flag stale listings based on age | Medium | v2.2.0 |
| Bulk generate: select multiple queued jobs, generate packs in sequence | Medium | v2.2.0 |

**Discovery strategy (preferred order):**
1. Manual URL paste (current, extended to store in `jobs` table)
2. Company career page RSS/Atom feeds where available
3. ATS API feeds (Greenhouse has a public JSON API per company)
4. Bookmarklet or browser extension to send a job page to Customy
5. LinkedIn scraping (deferred, see Phase 5)

### Phase 3 — Policy Engine and Application Resources (v2.3.x — v2.5.x)

Before any apply action, the system needs rules about what qualifies and what resources are available.

| Task | Priority | Version |
|------|----------|---------|
| Policy rules table: geography whitelist/blacklist, seniority range, company blacklist/whitelist, minimum fit score threshold, duplicate prevention rules | Critical | v2.3.0 |
| Human approval gates: no job moves to `ready_to_apply` without explicit approval; configurable per-policy (auto-approve above score X, manual below) | Critical | v2.3.0 |
| Answer bank: structured YAML of truthful answers to common application questions (work authorization, salary expectations, start date, relocation, visa status, language proficiency) | Critical | v2.4.0 |
| Candidate constraints: hard limits that auto-apply must never violate (e.g. minimum salary, location restrictions, visa requirements) | High | v2.4.0 |
| Resume/cover variants: ability to store and select from multiple tailored packs per job | Medium | v2.4.0 |
| Email templates: structured templates for outreach, follow-up, and thank-you emails | Medium | v2.5.0 |
| Form-answer provenance: every auto-filled answer must trace back to its source in the answer bank or candidate.yaml | High | v2.5.0 |
| Fail-safe behavior: if policy evaluation fails or data is missing, default to blocking the action and notifying the user | Critical | v2.5.0 |

### Phase 4 — Apply-Assist (v3.0.x — v3.2.x)

Human-supervised apply actions. Not autonomous.

| Task | Priority | Version |
|------|----------|---------|
| Apply-assist workflow: for a scored and approved job, prepare the application package (resume PDF, cover letter, filled form answers) and present for review | Critical | v3.0.0 |
| Direct-URL apply helper: open the application URL with pre-filled data where the ATS supports it | High | v3.0.0 |
| Email apply: draft and send application email using the prepared package, with human review before send | High | v3.1.0 |
| Application status tracking: link `jobs` table to `applications` table, track apply attempts and outcomes | High | v3.1.0 |
| Follow-up scheduler: draft follow-up emails at configurable intervals, with human approval | Medium | v3.2.0 |
| Full audit trail: every action (score, approve, generate, apply, follow-up) is logged with timestamp, actor (human/system), and evidence | Critical | v3.0.0 |

### Phase 5 — Limited Auto-Apply (v4.0.x)

Only after Phases 1-4 are stable and tested.

| Task | Priority | Version |
|------|----------|---------|
| Auto-apply mode: for jobs that pass all policy rules and score above a configurable threshold, automatically generate + apply without human review | High | v4.0.0 |
| Rate limiting: maximum N auto-applies per day, per company, per source | Critical | v4.0.0 |
| Kill switch: one-command disable of all auto-apply | Critical | v4.0.0 |
| Outcome feedback loop: track interview/offer/reject outcomes to refine scoring weights | High | v4.0.0 |
| LinkedIn scraping (optional): secondary account, headless browser, rate-limited — only if manual + ATS discovery is insufficient | Optional | v4.1.0 |
| Multi-source scraper: Indeed, Welcome to the Jungle, Rekrute, Bayt — only if justified by discovery gaps | Optional | v4.1.0 |
| Scheduled discovery: cron-based job intake from configured sources | Medium | v4.1.0 |

**What is explicitly deferred or avoided:**
- LangChain / LangGraph: not needed. The current `openai` SDK calls are clean and sufficient.
- Langfuse: useful for observability but not a prerequisite. Can be added at any point without architectural change.
- Docker / multi-user / tenant isolation: this is a different product. Deferred indefinitely.
- Broad LinkedIn scraping as a core strategy: high risk, high maintenance, fragile. Use only as a last resort.

---

## 3. Build Now / Defer Later / Avoid Entirely

| Item | Verdict | Reason |
|------|---------|--------|
| Regression tests | **Build now** | Zero tests exist. Any pipeline change is a blind deployment. |
| Evaluation samples | **Build now** | Needed to detect regressions in scoring and extraction. |
| Weighted scoring model | **Done** | Requirement coverage now drives the score instead of a flat candidate-keyword ratio. |
| Cross-language aliasing | **Build now** | Bilingual candidate applying to EN+FR jobs. Scores fragment without this. |
| Output quality gates | **Build now** | No automated check before writing artifacts. |
| Deterministic title normalization | **Build now** | Title variants split role detection and display. |
| Prompt hash tracking | **Build now** | Cheap to add, enables reproducibility. |
| Stronger requirement extraction | **Build now** | Some JD formats still produce empty `top_requirements`. |
| Job data model (`jobs` table) | **Build soon** | Foundation for everything after Phase 1. |
| Policy engine | **Build soon** | Cannot do any apply action without rules. |
| Answer bank | **Build soon** | Cannot fill application forms without truthful answers. |
| Company watchlist | **Build soon** | Higher signal than broad scraping. |
| ATS vendor detection | **Build soon** | Already partially implemented in URL parsing. |
| Batch regeneration | **Defer** | Polish feature. No quality impact. |
| A/B prompt comparison | **Defer** | Premature optimization of prompt engineering. |
| Generation diff view | **Defer** | Nice-to-have UI feature, not a quality gap. |
| CSV/JSON export | **Defer** | No current need for external analysis. |
| Config-driven model selection | **Defer** | Already supported via env vars. |
| LangChain integration | **Avoid** | Premature abstraction over clean SDK calls. |
| LangGraph agent workflow | **Avoid** | The state machine is two steps. This adds complexity without capability. |
| Langfuse observability | **Defer** | Useful but not blocking. Add when pipeline is stable. |
| LinkedIn scraping | **Defer** | High risk, fragile, unnecessary when ATS feeds and watchlists exist. |
| Anti-detection infrastructure | **Defer** | Only needed if scraping is needed, which it probably isn't yet. |
| Multi-source scraper | **Defer** | Only if discovery gaps justify the maintenance cost. |
| Docker packaging | **Avoid** | Single-user local app. Docker adds complexity without value. |
| Multi-user support | **Avoid** | Different product. Not this repo. |

---

## 4. Minimal Job Discovery + Apply Pipeline Schema

### `jobs` table

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),

    -- Identity & dedup
    url             TEXT,
    url_normalized  TEXT,
    dedupe_key      TEXT    NOT NULL UNIQUE,   -- hash(normalized_url OR company+title+location)

    -- Source
    source          TEXT    NOT NULL,           -- 'manual', 'ats_feed', 'career_page', 'linkedin', etc.
    source_detail   TEXT,                       -- specific feed URL, search query, etc.

    -- Job metadata
    company         TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    title_normalized TEXT,
    location        TEXT,
    remote          INTEGER NOT NULL DEFAULT 0,
    seniority       TEXT,                       -- 'junior', 'mid', 'senior', 'lead'
    language        TEXT,                       -- 'en', 'fr', 'ar'
    ats_vendor      TEXT,                       -- 'greenhouse', 'lever', 'workable', 'workday', etc.

    -- Content
    jd_raw          TEXT,
    jd_extracted_at TEXT,

    -- Scoring
    fit_score       REAL,
    score_detail    TEXT,                       -- JSON: breakdown of scoring components
    scored_at       TEXT,

    -- Pipeline status
    status          TEXT    NOT NULL DEFAULT 'new',
    -- 'new' -> 'scored' -> 'approved' -> 'generating' -> 'generated' -> 'ready_to_apply'
    --                                                                  -> 'applied' -> 'interviewing' -> 'offer'/'rejected'/'ghosted'
    -- 'new' -> 'scored' -> 'rejected_by_policy'
    -- 'new' -> 'scored' -> 'skipped'
    -- any -> 'expired'

    -- Approval
    approval_status TEXT    NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'auto_approved', 'rejected'
    approved_at     TEXT,
    approval_reason TEXT,

    -- Apply tracking
    apply_url       TEXT,                       -- direct application URL (may differ from listing URL)
    applied_at      TEXT,
    apply_method    TEXT,                       -- 'manual', 'email', 'ats_form', 'auto'
    application_id  INTEGER REFERENCES applications(id),

    -- Audit
    notes           TEXT,
    expires_at      TEXT
);
```

### `job_policy_rules` table

```sql
CREATE TABLE IF NOT EXISTS job_policy_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name       TEXT    NOT NULL UNIQUE,
    rule_type       TEXT    NOT NULL,           -- 'geography', 'seniority', 'company', 'score', 'rate_limit'
    rule_action     TEXT    NOT NULL,           -- 'require', 'block', 'flag'
    rule_config     TEXT    NOT NULL,           -- JSON: rule-specific configuration
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

### `answer_bank` table

```sql
CREATE TABLE IF NOT EXISTS answer_bank (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_key    TEXT    NOT NULL UNIQUE,    -- normalized question identifier
    question_text   TEXT    NOT NULL,           -- the actual question text
    answer_text     TEXT    NOT NULL,
    answer_source   TEXT    NOT NULL,           -- 'candidate_yaml', 'manual', 'derived'
    language        TEXT    NOT NULL DEFAULT 'en',
    category        TEXT,                       -- 'work_auth', 'salary', 'availability', 'relocation', etc.
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

### `audit_log` table

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    job_id          INTEGER REFERENCES jobs(id),
    application_id  INTEGER REFERENCES applications(id),
    action          TEXT    NOT NULL,           -- 'score', 'approve', 'generate', 'apply', 'follow_up', 'policy_block'
    actor           TEXT    NOT NULL,           -- 'human', 'system', 'auto_apply'
    detail          TEXT,                       -- JSON: action-specific context
    evidence        TEXT                        -- JSON: what data informed this action
);
```

---

## 5. Risk Section for Auto-Apply

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Hallucinated credentials**: LLM invents skills, metrics, or experience not in `candidate.yaml` | Critical | Output quality gates verify every skill traces to profile. Bullet fact-checking already exists in `_bullet_rewrite_is_safe`. Extend to cover all fields. |
| **Wrong language**: apply to a French job with an English resume or vice versa | High | Language purity gate already partially exists. Make it a hard block before write. |
| **Duplicate applications**: apply to the same job twice through different URLs | High | Dedupe key in `jobs` table. Fuzzy matching on company+title+location. Block generation if dedupe match exists. |
| **Applying to wrong seniority**: auto-apply to a Director role when candidate is a Lead | Medium | Seniority policy rule. Score penalty for seniority mismatch. |
| **Geography mismatch**: apply to jobs in locations where the candidate cannot work | Medium | Geography policy whitelist. Work authorization data in answer bank. |
| **Rate limiting / account bans**: too many applications from the same IP or account | High | Rate limit rule in policy engine. Maximum N per day per company per source. Exponential backoff. |
| **Stale listings**: apply to expired jobs | Low | Expiration tracking in `jobs` table. Flag jobs older than N days. |
| **Uncontrolled spend**: auto-apply triggers many LLM calls without oversight | Medium | Daily budget cap in policy engine. Kill switch for auto-apply. |
| **Audit failure**: cannot explain why a specific job was applied to | High | Full audit trail in `audit_log` table. Every action logged with evidence. |
| **Anti-pattern lock-in**: building scraping infrastructure that requires constant maintenance | Medium | Prefer ATS feeds and direct URLs over scraping. Scraping is deferred and optional. |
| **Legal/TOS risk**: scraping LinkedIn or other platforms violates TOS | High | LinkedIn scraping is explicitly optional/deferred. Use only with secondary account and clear consent to risk. |

---

## 6. Concrete Next 3 Implementation Milestones

### Milestone 1: Regression Tests + Evaluation Samples (v1.2.0-alpha)

**Goal:** Establish a safety net so pipeline changes are not blind deployments.

Build:
- `tests/test_analyzer.py`: test role extraction, company extraction, language detection, seniority detection, keyword matching, score calculation across 5+ representative JDs (EN/FR, structured/unstructured, with/without URLs).
- `tests/test_scoring.py`: test that score components behave correctly — keyword match ratio, seniority bonus, remote bonus, location bonus.
- `tests/test_targeting.py`: test `normalize_role_title`, `is_credible_role_title`, `prioritize_candidate_skills`, `candidate_keywords_from_profile`.
- `tests/test_models.py`: test `ApplicationPack.model_validate` and `TailoredExperience.model_validate` with valid, edge-case, and invalid inputs.
- `tests/fixtures/`: 5-10 saved JD texts with expected extraction results and scores.
- All tests runnable with `python -m pytest tests/` using only stdlib + pytest (no new dependencies beyond pytest).

### Milestone 2: Weighted Scoring + Cross-Language Aliasing (v1.2.0)

**Goal:** Make the fit score actually predictive of job relevance.

Build:
- Replace the flat `keyword_ratio * 60` formula in `analyze_jd` with a weighted model:
  - Requirement coverage: how many of the top requirements are addressed by candidate evidence (weight: 40%)
  - Keyword match depth: not just count but importance-weighted (JD-mentioned skills > nice-to-haves) (weight: 25%)
  - Seniority alignment: match vs. stretch vs. underqualified (weight: 15%)
  - Domain match: candidate experience domain vs. JD domain (weight: 10%)
  - Location/remote fit (weight: 10%)
- Build a bilingual alias map in `app/targeting.py`:
  - `{"machine learning": "apprentissage automatique", "data engineering": "ingénierie des données", ...}`
  - Use during keyword matching so `machine learning` in the JD matches `apprentissage automatique` in the candidate profile and vice versa.
- Update evaluation samples with expected scores under the new model.

### Milestone 3: Output Quality Gates (v1.3.0)

**Goal:** No artifact is written to disk unless it passes automated quality checks.

Build:
- Gate function in `app/generator.py` that runs after pack normalization and before `write_pack`:
  - Bullet count per experience matches source candidate profile
  - No bullet contains banned phrases
  - Summary is 2-3 sentences
  - Title passes `is_credible_role_title`
  - Resume language matches JD language (no mixed-language bullets)
  - All skills in `tailored_skills` exist in `candidate.yaml`
  - LaTeX renders without error (dry-run compile)
- If gate fails: log the failure reason, return a structured error to the user, do not write artifacts.
- Store prompt hash (SHA-256 of `system.md` content) per generation in `applications` table.

---

## 7. Versioning Plan (Corrected)

| Version | Milestone | Key Deliverable |
|---------|-----------|-----------------|
| v1.1.1 | **Current** | JD-to-evidence skill bridging + weighted scoring + exact-role title preservation |
| v1.2.0 | **Next** | Regression tests + cross-language aliasing |
| v1.3.0 | Quality gates | Output quality gates + prompt hash tracking + stronger requirement extraction |
| v1.4.0 | Score feedback | Score calibration feedback + deterministic title normalization |
| v2.0.0 | Job intake | `jobs` table + manual job intake + auto-scoring + dedupe |
| v2.1.0 | Discovery | ATS vendor detection + company watchlist + job queue dashboard view |
| v2.2.0 | Bulk ops | Bulk generate + job expiration tracking |
| v2.3.0 | Policy | Policy rules table + human approval gates |
| v2.4.0 | Resources | Answer bank + candidate constraints + resume variants |
| v2.5.0 | Audit | Form-answer provenance + fail-safe defaults |
| v3.0.0 | Apply-assist | Apply-assist workflow + direct-URL helper + audit trail |
| v3.1.0 | Email apply | Email apply with review + application status tracking |
| v3.2.0 | Follow-up | Follow-up scheduler with approval |
| v4.0.0 | Auto-apply | Limited auto-apply + rate limiting + kill switch + outcome feedback |

### Infrastructure Constraints (All Versions)

- Local-first: system runs on a single machine, no cloud dependency
- Zero/minimal cost: no paid SaaS unless strictly necessary
- SQLite: primary database through all versions
- No Flask, FastAPI, Django, Pydantic, or external web frameworks
- No new dependencies without explicit approval
- `candidate.yaml` remains the sole runtime source of truth for candidate data
- All outputs must be traceable to candidate evidence

---

## 8. Summary

The correct order is:

1. **First make customization reliably strong.** Fix scoring, add cross-language aliasing, add quality gates, write tests. This is Phase 1 and it must be done before anything else.
2. **Then add job intake and ranking.** Build the `jobs` table, manual intake, auto-scoring, dedup, and company watchlists. This is Phase 2.
3. **Then add approval + policy.** Build the policy engine, human approval gates, answer bank, and candidate constraints. This is Phase 3.
4. **Then add apply-assist.** Build the apply workflow, email apply, and audit trail with human review at every step. This is Phase 4.
5. **Only then add narrow auto-apply.** With rate limiting, kill switches, and outcome feedback. This is Phase 5.

Do not optimize for maximum automation first. Optimize for truthful outputs, auditability, and high-signal job selection first.
