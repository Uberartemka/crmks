-- Migration 007: machinery table (карта оборудования клиентов).
-- Idempotent (CREATE TABLE IF NOT EXISTS + guarded).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'machinery'
    ) THEN
        CREATE TABLE machinery (
            id            SERIAL PRIMARY KEY,
            client_id     INTEGER REFERENCES clients(id) ON DELETE CASCADE,
            created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
            name          VARCHAR(300) NOT NULL,
            node          VARCHAR(300),
            bearing       VARCHAR(300),
            brand         VARCHAR(100),
            install_date  VARCHAR(100),
            wear          INTEGER DEFAULT 0,
            status        VARCHAR(50) DEFAULT 'normal',
            created_at    VARCHAR(100),
            updated_at    VARCHAR(100)
        );
        CREATE INDEX idx_machinery_client ON machinery (client_id);
    END IF;
END $$;
