-- Migration 005: add client_id to users (links auth user → clients company).
-- Foundation for Group C domains (defects, orders, machinery bound to client company).
-- Idempotent: guarded by information_schema check.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'users'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'client_id'
        ) THEN
            ALTER TABLE users ADD COLUMN client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL;
        END IF;
    END IF;
END $$;
