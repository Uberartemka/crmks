-- Migration 011: user avatars. Idempotent (information_schema guard).
-- Assumes users + files tables exist (files from migration 010).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
          AND column_name = 'avatar_file_id'
    ) THEN
        ALTER TABLE users
            ADD COLUMN avatar_file_id BIGINT NULL REFERENCES files(id) ON DELETE SET NULL;
    END IF;
END $$;
