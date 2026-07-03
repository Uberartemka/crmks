-- Migration 003: unified relational catalog
-- Idempotent: every CREATE guards on existence.
-- Replaces the flat sku_catalog for new logic; old table stays until sites migrate.

-- 1. brands
CREATE TABLE IF NOT EXISTS brands (
    id      serial PRIMARY KEY,
    name    text NOT NULL UNIQUE,
    slug    text UNIQUE
);

-- 2. categories (with self-reference for nesting)
CREATE TABLE IF NOT EXISTS categories (
    id        serial PRIMARY KEY,
    name      text NOT NULL,
    slug      text UNIQUE,
    title     text,
    parent_id integer REFERENCES categories(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories (parent_id);

-- 3. products (flat table with full bearing specs + FKs)
CREATE TABLE IF NOT EXISTS products (
    id            serial PRIMARY KEY,
    category_id   integer REFERENCES categories(id) ON DELETE SET NULL,
    brand_id      integer REFERENCES brands(id) ON DELETE SET NULL,
    code          text NOT NULL,
    name          text NOT NULL,
    weight        numeric(10,4),
    d             numeric(10,2),
    d_outer       numeric(10,2),
    b_width       numeric(10,2),
    rs_min        numeric(10,2),
    static_load   numeric(10,2),
    dynamic_load  numeric(10,2),
    rpm_oil       integer,
    rpm_grease    integer,
    seal_type     text,
    price_old     numeric(12,2),
    price_new     numeric(12,2),
    stock         integer NOT NULL DEFAULT 0,
    is_active     boolean NOT NULL DEFAULT true,
    application   text[] NOT NULL DEFAULT '{}',
    img           text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (code, brand_id)
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_products_brand    ON products (brand_id);
CREATE INDEX IF NOT EXISTS idx_products_active   ON products (is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_products_code     ON products (code);
