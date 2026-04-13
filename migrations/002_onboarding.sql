-- Customy V3 — Onboarding tables
-- Run after migrations/001_initial.sql in the Supabase SQL editor.

-- resume_uploads: stores original resume files uploaded by users
CREATE TABLE IF NOT EXISTS resume_uploads (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    storage_path       TEXT NOT NULL,
    original_filename  TEXT NOT NULL,
    file_size_bytes    INTEGER,
    parse_status       TEXT NOT NULL DEFAULT 'pending',
    -- parse_status values: pending | done | failed
    parsed_text        TEXT,
    parse_error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_resume_uploads_user ON resume_uploads(user_id);
ALTER TABLE resume_uploads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS resume_uploads_user ON resume_uploads;
CREATE POLICY resume_uploads_user ON resume_uploads
    USING (user_id = auth.uid());

-- onboarding_drafts: per-user scratch space during the onboarding flow.
-- One row per user (UNIQUE on user_id). Mutable until status = 'complete'.
-- Promoted to profiles on completion (Phase 3). Never used for generation directly.
CREATE TABLE IF NOT EXISTS onboarding_drafts (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_resume_upload_id   UUID REFERENCES resume_uploads(id),
    status                    TEXT NOT NULL DEFAULT 'draft',
    -- status values: draft | questions_pending | questions_answered | enriching | complete
    draft_data                JSONB NOT NULL DEFAULT '{}',
    gap_analysis              JSONB NOT NULL DEFAULT '{}',
    user_answers              JSONB NOT NULL DEFAULT '{}'
);
ALTER TABLE onboarding_drafts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS onboarding_drafts_user ON onboarding_drafts;
CREATE POLICY onboarding_drafts_user ON onboarding_drafts
    USING (user_id = auth.uid());
