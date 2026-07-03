-- Migration 002: add application text[] column to sku_catalog
-- Idempotent. Mirrors the production schema on the sites server (hhb_b2b)
-- so that catalog data imported from there preserves the "application"
-- field (array of usage domains, e.g. {"Универсальное применение"}).
-- Also tolerant: if sku_catalog does not exist (fresh test DB), no-op.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sku_catalog' AND column_name = 'application'
    ) THEN
        -- already has the column, nothing to do
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'sku_catalog'
    ) THEN
        ALTER TABLE sku_catalog ADD COLUMN application text[];
    END IF;
END $$;
