-- Migration 004: point proposal_items.sku_id at the unified products table
-- (was: sku_catalog(id) ON DELETE CASCADE; now: products(id) ON DELETE RESTRICT).
--
-- Idempotent and safe on a fresh DB: every step is guarded by checks against
-- information_schema / pg_constraint. Safe to re-run.
--
-- Note: products and proposal_items tables must already exist (created by
-- migration 003 and startup/db_init respectively). If proposal_items does not
-- exist yet, this migration is a no-op (it'll be applied again on next start
-- once db_init has created the table).

DO $$
BEGIN
    -- 1. Only proceed if proposal_items exists.
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'proposal_items'
    ) THEN
        -- 2. Drop the OLD FK constraint(s) that point proposal_items.sku_id at sku_catalog.
        --    Name is stable (db_init / schema.sql: proposal_items_sku_id_fkey).
        IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'proposal_items_sku_id_fkey'
        ) THEN
            ALTER TABLE proposal_items DROP CONSTRAINT proposal_items_sku_id_fkey;
        END IF;

        -- 3. Add the NEW FK to products(id) ON DELETE RESTRICT, if not already present.
        --    (RESTRICT protects historical proposals: a product referenced by a KP
        --    cannot be deleted without first unlinking the KP.)
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'proposal_items_sku_id_fkey'
              AND conrelid = 'proposal_items'::regclass
              AND confrelid = 'products'::regclass
        ) THEN
            ALTER TABLE proposal_items
                ADD CONSTRAINT proposal_items_sku_id_fkey
                FOREIGN KEY (sku_id) REFERENCES products(id) ON DELETE RESTRICT;
        END IF;
    END IF;
END $$;
