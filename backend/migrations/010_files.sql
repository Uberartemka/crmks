-- Migration 010: universal file storage (Подсистема II).
-- Idempotent (information_schema guard). Assumes users table exists.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'files'
    ) THEN
        CREATE TABLE files (
            id              BIGSERIAL PRIMARY KEY,
            uploaded_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            -- relative path under MEDIA_ROOT (e.g. "2026/07/abc123def456.pdf")
            storage_path    TEXT NOT NULL,
            thumbnail_path  TEXT NULL,
            original_name   TEXT NOT NULL,
            mime_type       TEXT NOT NULL,
            size_bytes      BIGINT NOT NULL,
            sha256          TEXT NOT NULL,
            is_image        BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_files_uploaded_by ON files (uploaded_by);
        CREATE INDEX idx_files_sha256 ON files (sha256);
    END IF;
END $$;
