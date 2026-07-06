-- Migration 012: chat message attachments (Подсистема II — интеграция).
-- Idempotent: ADD COLUMN IF NOT EXISTS (PG 9.6+), CREATE INDEX IF NOT EXISTS (PG 9.5+).
-- Assumes messages (009) and files (010) tables exist.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS attachment_id
    BIGINT NULL REFERENCES files(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_messages_attachment
    ON messages (attachment_id) WHERE attachment_id IS NOT NULL;
