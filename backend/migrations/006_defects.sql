-- Migration 006: defects table (дефектовка оборудования клиентов).
-- Idempotent (CREATE TABLE IF NOT EXISTS + guarded).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'defects'
    ) THEN
        CREATE TABLE defects (
            id          SERIAL PRIMARY KEY,
            client_id   INTEGER REFERENCES clients(id) ON DELETE CASCADE,
            created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
            equipment   VARCHAR(300) NOT NULL,
            bearing     VARCHAR(300),
            description TEXT,
            status      VARCHAR(50) DEFAULT 'new',
            action      TEXT,
            detected_at VARCHAR(100),
            created_at  VARCHAR(100),
            updated_at  VARCHAR(100)
        );
        CREATE INDEX idx_defects_client ON defects (client_id);
        CREATE INDEX idx_defects_status ON defects (status);
    END IF;
END $$;
