-- Migration 001: watchdog support for job_queue
-- Idempotent: each statement guards on existence before altering.
-- Converts varchar timestamps to timestamptz, adds claimed_at / process_after.

-- 1. Add claimed_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'claimed_at'
    ) THEN
        ALTER TABLE job_queue ADD COLUMN claimed_at timestamptz;
    END IF;
END $$;

-- 2. Add process_after (default now so existing rows are immediately claimable)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'process_after'
    ) THEN
        ALTER TABLE job_queue ADD COLUMN process_after timestamptz NOT NULL DEFAULT now();
    END IF;
END $$;

-- 3. Convert created_at varchar -> timestamptz
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'created_at'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE job_queue ALTER COLUMN created_at TYPE timestamptz
            USING created_at::timestamptz;
        ALTER TABLE job_queue ALTER COLUMN created_at SET DEFAULT now();
    END IF;
END $$;

-- 4. Convert updated_at varchar -> timestamptz
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'updated_at'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE job_queue ALTER COLUMN updated_at TYPE timestamptz
            USING updated_at::timestamptz;
        ALTER TABLE job_queue ALTER COLUMN updated_at SET DEFAULT now();
    END IF;
END $$;

-- 5. Partial index for watchdog + worker claims
CREATE INDEX IF NOT EXISTS idx_job_queue_claim
    ON job_queue (status, process_after)
    WHERE status IN ('pending', 'processing');
