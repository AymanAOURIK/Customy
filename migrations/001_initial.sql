-- Customy V3 — Initial Postgres Schema
-- Run this once in the Supabase SQL editor.
-- Supabase Auth handles auth.users automatically.

-- profiles: replaces candidate.yaml
CREATE TABLE IF NOT EXISTS profiles (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    full_name         TEXT NOT NULL,
    email             TEXT,
    phone             TEXT,
    location          TEXT,
    linkedin          TEXT,
    github            TEXT,
    headline          TEXT,
    summary           TEXT,
    skills            JSONB NOT NULL DEFAULT '{}',
    experiences       JSONB NOT NULL DEFAULT '[]',
    education         JSONB NOT NULL DEFAULT '[]',
    spoken_languages  JSONB NOT NULL DEFAULT '[]',
    scoring_keywords  JSONB NOT NULL DEFAULT '[]'
);

-- jobs: independent of generation
CREATE TABLE IF NOT EXISTS jobs (
    id                  SERIAL PRIMARY KEY,
    user_id             UUID NOT NULL REFERENCES auth.users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source              TEXT NOT NULL,
    source_url          TEXT,
    fingerprint         TEXT NOT NULL,
    title               TEXT NOT NULL,
    company             TEXT,
    location_raw        TEXT,
    description_text    TEXT NOT NULL,
    posted_date         TEXT,
    salary_raw          TEXT,
    status              TEXT NOT NULL DEFAULT 'saved',
    relevance_score     REAL,
    jd_analysis_json    TEXT,
    structured_job_json TEXT,
    application_id      INTEGER,
    notes               TEXT,
    CONSTRAINT jobs_user_fingerprint_unique UNIQUE (user_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);

-- applications: core artifact table with user_id
CREATE TABLE IF NOT EXISTS applications (
    id                    SERIAL PRIMARY KEY,
    user_id               UUID NOT NULL REFERENCES auth.users(id),
    job_id                INTEGER REFERENCES jobs(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    company               TEXT NOT NULL,
    role                  TEXT NOT NULL,
    slug                  TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'generated',
    is_duplicate          INTEGER NOT NULL DEFAULT 0,
    jd_raw                TEXT NOT NULL,
    jd_language           TEXT,
    jd_location           TEXT,
    job_application_url   TEXT,
    resume_tex_url        TEXT,
    resume_pdf_url        TEXT,
    cover_letter_url      TEXT,
    linkedin_msg_url      TEXT,
    email_draft_url       TEXT,
    cover_letter          BOOLEAN NOT NULL DEFAULT FALSE,
    linkedin_msg          BOOLEAN NOT NULL DEFAULT FALSE,
    email_draft           BOOLEAN NOT NULL DEFAULT FALSE,
    tokens_used           INTEGER,
    model_used            TEXT,
    score                 REAL,
    initial_score         REAL,
    updated_score         REAL,
    notes                 TEXT,
    prompt_tokens         INTEGER,
    cached_prompt_tokens  INTEGER,
    completion_tokens     INTEGER,
    input_cost_usd        REAL,
    cached_input_cost_usd REAL,
    output_cost_usd       REAL,
    total_cost_usd        REAL,
    api_attempts          INTEGER,
    pricing_basis         TEXT,
    role_archetype        TEXT,
    CONSTRAINT applications_user_slug_unique UNIQUE (user_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);

-- interview_prep: on-demand prep generation
CREATE TABLE IF NOT EXISTS interview_prep (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    prep_level      TEXT NOT NULL,
    stage           TEXT NOT NULL,
    prep_json       TEXT NOT NULL,
    tokens_used     INTEGER,
    model_used      TEXT,
    total_cost_usd  REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_interview_prep_user ON interview_prep(user_id);

-- events: application status change log
CREATE TABLE IF NOT EXISTS events (
    id              SERIAL PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      TEXT NOT NULL,
    old_status      TEXT,
    new_status      TEXT,
    detail          TEXT
);

-- daily_stats: per-user activity aggregates
CREATE TABLE IF NOT EXISTS daily_stats (
    user_id      UUID NOT NULL REFERENCES auth.users(id),
    date         DATE NOT NULL,
    generated    INTEGER NOT NULL DEFAULT 0,
    applied      INTEGER NOT NULL DEFAULT 0,
    interviews   INTEGER NOT NULL DEFAULT 0,
    offers       INTEGER NOT NULL DEFAULT 0,
    rejections   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

-- api_usage: per-request token and cost tracking
CREATE TABLE IF NOT EXISTS api_usage (
    id                    SERIAL PRIMARY KEY,
    user_id               UUID NOT NULL REFERENCES auth.users(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    application_id        INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    request_kind          TEXT NOT NULL,
    request_status        TEXT NOT NULL DEFAULT 'succeeded',
    error_message         TEXT,
    attempt_number        INTEGER NOT NULL DEFAULT 1,
    model_used            TEXT,
    prompt_tokens         INTEGER NOT NULL DEFAULT 0,
    cached_prompt_tokens  INTEGER NOT NULL DEFAULT 0,
    completion_tokens     INTEGER NOT NULL DEFAULT 0,
    total_tokens          INTEGER NOT NULL DEFAULT 0,
    input_cost_usd        REAL,
    cached_input_cost_usd REAL,
    output_cost_usd       REAL,
    total_cost_usd        REAL,
    pricing_basis         TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_usage_user_id ON api_usage(user_id);

-- admin_ideas: future ideas board (no RLS — admin-only via service role)
CREATE TABLE IF NOT EXISTS admin_ideas (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    title           TEXT NOT NULL,
    description     TEXT,
    category        TEXT,
    priority        TEXT,
    status          TEXT NOT NULL DEFAULT 'idea',
    target_version  TEXT
);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS profiles_user ON profiles;
CREATE POLICY profiles_user ON profiles USING (user_id = auth.uid());

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS jobs_user ON jobs;
CREATE POLICY jobs_user ON jobs USING (user_id = auth.uid());

ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS applications_user ON applications;
CREATE POLICY applications_user ON applications USING (user_id = auth.uid());

ALTER TABLE interview_prep ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS interview_prep_user ON interview_prep;
CREATE POLICY interview_prep_user ON interview_prep USING (user_id = auth.uid());

ALTER TABLE daily_stats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS daily_stats_user ON daily_stats;
CREATE POLICY daily_stats_user ON daily_stats USING (user_id = auth.uid());

ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_usage_user ON api_usage;
CREATE POLICY api_usage_user ON api_usage USING (user_id = auth.uid());

-- Storage: artifacts bucket policy
-- Run separately after creating the 'artifacts' bucket in Supabase Storage:
--
-- CREATE POLICY storage_user ON storage.objects
--   USING (bucket_id = 'artifacts'
--     AND (storage.foldername(name))[1] = auth.uid()::text);
