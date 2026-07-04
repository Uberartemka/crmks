-- Migration 008: orders table (заказы клиентов).
-- Idempotent (CREATE TABLE IF NOT EXISTS + guarded).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'orders'
    ) THEN
        CREATE TABLE orders (
            id            SERIAL PRIMARY KEY,
            client_id     INTEGER REFERENCES clients(id) ON DELETE CASCADE,
            created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
            order_number  VARCHAR(100),
            name          VARCHAR(500) NOT NULL,
            qty           INTEGER DEFAULT 1,
            total         NUMERIC(14,2) DEFAULT 0,
            status        VARCHAR(50) DEFAULT 'new',
            order_date    VARCHAR(100),
            created_at    VARCHAR(100),
            updated_at    VARCHAR(100)
        );
        CREATE INDEX idx_orders_client ON orders (client_id);
        CREATE INDEX idx_orders_status ON orders (status);
    END IF;
END $$;
