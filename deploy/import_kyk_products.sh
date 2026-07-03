#!/usr/bin/env bash
# One-shot: выгрузить kyk.products (с JOIN brand/category) с сайт-сервера
# и загрузить во временную staging-таблицу kyk_products_import в CRM БД.
#
# Запуск: с любой машины, имеющей SSH-ключ к сайт-серверу и psql к CRM.
#   bash deploy/import_kyk_products.sh
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/kyk_server_key}"
SITES_HOST="${SITES_HOST:-root@193.164.149.3}"
KYK_PG_PASSWORD="${KYK_PG_PASSWORD:-KykProd2026}"   # из /var/www/kyk/.env на сайт-сервере

# CRM DSN берётся из .env так же, как в import_catalog.py
if [ -d /var/www/crmks ]; then
  CRM_DSN="$(grep '^DATABASE_URL=' /var/www/crmks/backend/.env | cut -d= -f2-)"
else
  CRM_DSN="$(grep '^DATABASE_URL=' backend/.env | cut -d= -f2-)"
fi

WORK="$(mktemp -d)"
CSV="$WORK/kyk_products_export.csv"
trap 'rm -rf "$WORK"' EXIT

echo "[import-kyk] 1/3 Выгрузка с сайт-сервера (COPY с JOIN)..."
ssh -i "$SSH_KEY" "$SITES_HOST" \
  "PGPASSWORD='$KYK_PG_PASSWORD' psql -h localhost -U kyk -d kyk -c \"COPY (SELECT p.id, p.code, p.name, c.name AS category, b.name AS brand, p.weight, p.price_old, p.price_new, p.d, p.d_outer, p.b_width, p.rs_min, p.static_load, p.dynamic_load, p.rpm_oil, p.rpm_grease, p.seal_type, p.created_at, p.updated_at, p.stock, p.is_active FROM products p LEFT JOIN categories c ON c.id = p.category_id LEFT JOIN brands b ON b.id = p.brand_id ORDER BY p.id) TO STDOUT WITH CSV HEADER\"" \
  > "$CSV"

ROWS=$(($(wc -l < "$CSV") - 1))   # минус HEADER
echo "[import-kyk]    выгружено строк: $ROWS (ожидается ~735)"

echo "[import-kyk] 2/3 Создание/TRUNCATE staging в CRM..."
psql "$CRM_DSN" <<'SQL'
CREATE TABLE IF NOT EXISTS kyk_products_import (
    id          integer,
    code        text,
    name        text,
    category    text,
    brand       text,
    weight      real,
    price_old   real,
    price_new   real,
    d           real,
    d_outer     real,
    b_width     real,
    rs_min      real,
    static_load real,
    dynamic_load real,
    rpm_oil     integer,
    rpm_grease  integer,
    seal_type   text,
    created_at  bigint,
    updated_at  bigint,
    stock       integer,
    is_active   boolean
);
TRUNCATE kyk_products_import;
SQL

echo "[import-kyk] 3/3 Загрузка CSV в staging..."
psql "$CRM_DSN" -v ON_ERROR_STOP=1 -c "\copy kyk_products_import FROM '$CSV' WITH CSV HEADER"

echo "[import-kyk] Готово. Проверка:"
psql "$CRM_DSN" -c "SELECT count(*) AS rows, count(*) FILTER (WHERE is_active) AS active, count(*) FILTER (WHERE price_new IS NOT NULL) AS with_price FROM kyk_products_import;"
echo "[import-kyk] Теперь запусти трансформер: cd backend && python -m scripts.import_kyk_products"
