# Import kyk.products → CRM unified catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести 735 товаров из БД `kyk` (сайты-сервер `193.164.149.3`) в CRM `products`, обогатив существующие записи характеристиками подшипников (`rs_min`, `static_load`, `dynamic_load`, `rpm_oil`, `rpm_grease`, `seal_type`, `weight`, `d`, `d_outer`, `b_width`) и добавив недостающие коды.

**Architecture:** Двухфазный импорт по образцу `scripts/import_catalog.py`:
1. **Доставка (Task 0):** `COPY ... TO STDOUT` с JOIN по `categories`/`brands` на сайт-сервере → CSV → загрузка во временную staging-таблицу `kyk_products_import` в CRM-БД. Текстовые имена brand/category (как в `import_from_sku_catalog`), а не id — избавляет от конфликта справочников.
2. **Трансформация (Task 2):** локальный скрипт `scripts/import_kyk_products.py` читает staging, для каждого code: если продукт `(code, brand)` уже есть — `UPDATE ... SET f = COALESCE(products.f, src.f)` (обогащает только NULL-поля, не затирая заполненные); если нет — `INSERT`. Brand/category lookup **case-insensitive** (`LOWER(name)`), чтобы `'Kyk'` нашёл существующий `'KYK'`. Timestamps `bigint` (Unix-sec) → `to_timestamp()` → `timestamptz`.

**Tech Stack:** Python 3, psycopg2 (raw SQL, без ORM — как в `import_catalog.py`), pytest + PostgreSQL test DB, bash + `psql`/`COPY` для доставки.

**Принятые решения (из уточнения с заказчиком):**
- Дубликаты `(code, brand=KYK)` → **обогащать характеристики**, не затирая уже заполненные поля (COALESCE, приёмник приоритетнее).
- Объём → **все 735**, сохранить `is_active` из источника (650 как скрытые/черновики).
- Цены → **перенос 1:1** (`price_new`/`price_old`); retail/wholesale — отдельная миграция позже (вместе с мультитенантностью).

---

## File Structure

| Файл | Ответственность | Статус |
|---|---|---|
| `backend/scripts/import_kyk_products.py` | Скрипт-трансформер: staging → products (insert/enrich), case-insensitive brand/category, timestamp-конверсия | **Create** |
| `backend/tests/test_import_kyk_products.py` | Тесты: маппинг характеристик, enrich без затирания, case-insensitive brand, идемпотентность, timestamp-конверсия, guard на отсутствие staging | **Create** |
| `backend/tests/conftest.py` | Добавить `kyk_products_import` в `_TABLES_TO_CLEAR`, чтобы `db_conn`-фикстура чистила staging между тестами | **Modify** (1 строка) |
| `deploy/import_kyk_products.sh` | Bash-скрипт доставки: COPY с JOIN на сайт-сервере → CSV → CREATE+TRUNCATE staging на CRM → `\copy` загрузка | **Create** |

Staging-таблица `kyk_products_import` **не является миграцией** — это разовая таблица, создаётся скриптом доставки и в тестах фикстурой вручную. После импорта её можно дропнуть (Task 3, cleanup).

---

## Task 0: Доставка данных (операционный, выполняется на серверах)

**Files:**
- Create: `deploy/import_kyk_products.sh`

Этот task — bash-скрипт + его ручной прогон. Не покрывается unit-тестами (трогает живые сервера); корректность трансформации проверяется тестами в Task 2 на синтетической staging-таблице.

- [ ] **Step 1: Создать bash-скрипт доставки**

`deploy/import_kyk_products.sh`:
```bash
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
```

- [ ] **Step 2: Сделать исполняемым и закоммитить**

```bash
chmod +x deploy/import_kyk_products.sh
git add deploy/import_kyk_products.sh
git commit -m "chore: add kyk.products delivery script (sites -> CRM staging)"
```

- [ ] **Step 3: Прогнать на проде (фактический запуск — в Task 3)**

Сам запуск скрипта и заливка в staging выполняется на финальном шаге деплоя (Task 3, Step 1). Здесь скрипт только создан и закоммичен.

---

## Task 1: Подключить staging к тестовой инфраструктуре

**Files:**
- Modify: `backend/tests/conftest.py:17`

- [ ] **Step 1: Добавить `kyk_products_import` в `_TABLES_TO_CLEAR`**

В `backend/tests/conftest.py` строка 17:
```python
# Было:
_TABLES_TO_CLEAR = ["products", "categories", "brands", "sku_catalog", "job_queue"]

# Стало:
_TABLES_TO_CLEAR = ["products", "categories", "brands", "sku_catalog", "kyk_products_import", "job_queue"]
```

Это нужно, чтобы фикстура `db_conn` (которой пользуются все тесты) чистила staging между прогонами. Без этого тесты импорта kyk будут течь в другие тесты.

- [ ] **Step 2: Проверить, что существующие тесты не сломались**

Run: `cd backend && python -m pytest -q`
Expected: 60 passed (ничего не должно измениться — новой таблицы в схеме ещё нет, `to_regclass` вернёт NULL и TRUNCATE пропустится через существующий guard).

- [ ] **Step 3: Коммит**

```bash
git add backend/tests/conftest.py
git commit -m "test: clear kyk_products_import staging between tests"
```

---

## Task 2: Скрипт-трансформер `import_kyk_products.py` (TDD)

**Files:**
- Create: `backend/scripts/import_kyk_products.py`
- Test: `backend/tests/test_import_kyk_products.py`

### Часть A: Фикстура и тесты (RED)

- [ ] **Step 1: Создать тест-файл с фикстурой и всеми тестами**

`backend/tests/test_import_kyk_products.py`:
```python
"""Tests for the kyk.products import script.

The import reads from a staging table `kyk_products_import` (loaded via
deploy/import_kyk_products.sh from the remote sites server) and writes into
the unified products/brands/categories tables. Existing rows matching
(code, brand) are ENRICHED — NULL characteristic fields filled from source,
non-NULL fields preserved. Brand/category lookup is case-insensitive so
'Kyk' resolves to an existing 'KYK' brand instead of duplicating.
"""
import pytest

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003,
)
from scripts.import_kyk_products import import_from_kyk


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


@pytest.fixture
def seeded_kyk_import(db_conn):
    """Recreate kyk_products_import staging and seed rows that exercise
    insert / enrich / case-insensitive-brand / inactive paths."""
    _apply_all_migrations(db_conn)
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS kyk_products_import")
    # Mirror of the staging schema produced by deploy/import_kyk_products.sh.
    cur.execute(
        """
        CREATE TABLE kyk_products_import (
            id integer,
            code text,
            name text,
            category text,
            brand text,
            weight real,
            price_old real,
            price_new real,
            d real,
            d_outer real,
            b_width real,
            rs_min real,
            static_load real,
            dynamic_load real,
            rpm_oil integer,
            rpm_grease integer,
            seal_type text,
            created_at bigint,
            updated_at bigint,
            stock integer,
            is_active boolean
        )
        """
    )
    # Row 1: brand-new active product with full characteristics.
    # Row 2: brand-new inactive product, no prices (mirrors the 650 hidden).
    # Row 3: same code as a pre-existing KYK product WITHOUT characteristics
    #        → must enrich, not duplicate.
    cur.execute(
        """
        INSERT INTO kyk_products_import
            (id, code, name, category, brand, weight, price_old, price_new,
             d, d_outer, b_width, rs_min, static_load, dynamic_load,
             rpm_oil, rpm_grease, seal_type, created_at, updated_at, stock, is_active)
        VALUES
            (10, '6203 ZZ', 'Подшипник 6203 ZZ', 'Шарикоподшипники с глубоким желобом', 'Kyk',
             0.30, 110.0, 95.0, 17, 40, 12, 0.5, 6.2, 9.5, 14000, 11000, 'ZZ',
             1685448531, 1685448531, 300, true),
            (11, '604', 'Подшипник 604', 'Миниатюрные шарикоподшипники', 'Kyk',
             0.0021, NULL, NULL, 4, 12, 4, 0.2, 0.36, 0.97, 63000, 53000, 'Открытый',
             1685448531, 1685448531, 0, false),
            (12, '605', 'Подшипник 605 (source)', 'Миниатюрные шарикоподшипники', 'Kyk',
             0.0025, 50.0, 45.0, 5, 14, 5, 0.3, 0.5, 1.2, 60000, 50000, 'ZZ',
             1685448531, 1685448531, 10, true)
        """
    )
    # Pre-existing KYK product with NO characteristics — target for enrichment.
    # Note brand created as 'KYK' (uppercase) to test case-insensitive match.
    cur.execute("INSERT INTO brands (name, slug) VALUES ('KYK', 'kyk') RETURNING id")
    kyk_brand_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO products (code, name, brand_id, rs_min) VALUES ('605', 'Подшипник 605 (existing)', %s, 999)",
        (kyk_brand_id,),
    )
    # Clean any other products/categories so assertions are deterministic.
    cur.execute("DELETE FROM products WHERE code NOT IN ('605')")
    cur.execute("DELETE FROM categories")
    cur.close()
    return db_conn


def test_import_inserts_new_products(seeded_kyk_import):
    conn = seeded_kyk_import
    stats = import_from_kyk(conn)
    # Rows 1 ('6203 ZZ') and 2 ('604') are new; row 3 ('605') enriches existing.
    assert stats["inserted"] == 2
    assert stats["enriched"] == 1
    assert stats["errors"] == 0


def test_import_maps_all_characteristics(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT weight, d, d_outer, b_width, rs_min, static_load, dynamic_load,
               rpm_oil, rpm_grease, seal_type
        FROM products WHERE code = '6203 ZZ'
        """
    )
    (weight, d, d_outer, b_width, rs_min, static_load, dynamic_load,
     rpm_oil, rpm_grease, seal_type) = cur.fetchone()
    cur.close()
    assert float(weight) == 0.30
    assert float(d) == 17
    assert float(d_outer) == 40
    assert float(b_width) == 12
    assert float(rs_min) == 0.5
    assert float(static_load) == 6.2
    assert float(dynamic_load) == 9.5
    assert rpm_oil == 14000
    assert rpm_grease == 11000
    assert seal_type == "ZZ"


def test_import_preserves_prices_and_stock(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT price_old, price_new, stock FROM products WHERE code='6203 ZZ'")
    price_old, price_new, stock = cur.fetchone()
    cur.close()
    assert float(price_old) == 110.0
    assert float(price_new) == 95.0
    assert stock == 300


def test_import_preserves_is_active(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT is_active FROM products WHERE code IN ('6203 ZZ','604') ORDER BY code")
    states = [r[0] for r in cur.fetchall()]
    cur.close()
    assert states == [False, True]   # '604' false, '6203 ZZ' true (ordered by code)


def test_import_converts_unix_timestamps(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM products WHERE code='6203 ZZ'")
    created_at = cur.fetchone()[0]
    cur.close()
    # 1685448531 epoch -> 2023-05-30 10:48:51 UTC
    assert created_at.year == 2023
    assert created_at.month == 5


def test_import_enriches_existing_without_overwriting(seeded_kyk_import):
    """Existing '605' (rs_min=999) must be enriched with the other NULL fields,
    but rs_min must NOT be overwritten by source (0.3)."""
    conn = seeded_kyk_import
    stats = import_from_kyk(conn)
    assert stats["enriched"] == 1
    cur = conn.cursor()
    cur.execute(
        "SELECT rs_min, static_load, dynamic_load, d, d_outer, name FROM products WHERE code='605'"
    )
    rs_min, static_load, dynamic_load, d, d_outer, name = cur.fetchone()
    cur.close()
    # Source rs_min=0.3 must NOT overwrite the existing 999.
    assert float(rs_min) == 999
    # But NULL fields are filled from source.
    assert float(static_load) == 0.5
    assert float(dynamic_load) == 1.2
    assert float(d) == 5
    assert float(d_outer) == 14
    # Name (non-NULL) is preserved — source name not forced in.
    assert name == "Подшипник 605 (existing)"


def test_import_resolves_brand_case_insensitive(seeded_kyk_import):
    """Source brand 'Kyk' must resolve to pre-existing 'KYK', not duplicate."""
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM brands WHERE LOWER(name) = 'kyk'")
    n = cur.fetchone()[0]
    cur.close()
    assert n == 1


def test_import_creates_categories(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT name FROM categories ORDER BY name")
    names = {r[0] for r in cur.fetchall()}
    cur.close()
    assert "Шарикоподшипники с глубоким желобом" in names
    assert "Миниатюрные шарикоподшипники" in names


def test_import_is_idempotent(seeded_kyk_import):
    conn = seeded_kyk_import
    first = import_from_kyk(conn)
    second = import_from_kyk(conn)
    assert first["inserted"] == 2
    # Second run: nothing new inserted; existing rows re-enriched (no-op COALESCE).
    assert second["inserted"] == 0
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM products WHERE code IN ('6203 ZZ','604','605')")
    assert cur.fetchone()[0] == 3
    cur.close()


def test_import_no_staging_returns_empty(db_conn):
    """If staging table is absent, import is a no-op with empty stats."""
    _apply_all_migrations(db_conn)
    # Do NOT create kyk_products_import.
    stats = import_from_kyk(db_conn)
    assert stats == {"inserted": 0, "enriched": 0, "errors": 0}


def test_import_skips_rows_without_code(seeded_kyk_import):
    """Rows with NULL code must be skipped, not crash the import."""
    conn = seeded_kyk_import
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO kyk_products_import (id, code, name, brand) VALUES (99, NULL, 'no code', 'Kyk')"
    )
    cur.close()
    stats = import_from_kyk(conn)
    # Same 2 inserts + 1 enrich as before; the NULL-code row is filtered in SELECT.
    assert stats["inserted"] == 2
    assert stats["errors"] == 0
```

- [ ] **Step 2: Прогнать тесты — должны упасть (модуль не существует)**

Run: `cd backend && python -m pytest tests/test_import_kyk_products.py -v`
Expected: ERROR/FAIL — `ModuleNotFoundError: No module named 'scripts.import_kyk_products'`

### Часть B: Реализация (GREEN)

- [ ] **Step 3: Создать скрипт `import_kyk_products.py`**

`backend/scripts/import_kyk_products.py`:
```python
"""One-shot import: kyk.products (from sites server) → unified products.

Reads from a staging table `kyk_products_import` that must be loaded into the
local CRM DB beforehand (see deploy/import_kyk_products.sh). For each row:

- If a product matching (code, brand_id) exists → ENRICH: fill only the NULL
  characteristic/price/stock fields from the source (COALESCE — receiver wins,
  non-NULL fields are never overwritten).
- Otherwise → INSERT a new product carrying all fields from the source.

Brand and category lookup are CASE-INSENSITIVE (LOWER(name)) so that a source
brand 'Kyk' resolves to a pre-existing 'KYK' instead of creating a duplicate.
`created_at`/`updated_at` arrive as Unix seconds (bigint) and are converted via
to_timestamp().

Idempotent: re-running inserts nothing new (existing rows are re-enriched with
no-op COALESCE). Returns stats: {"inserted", "enriched", "errors"}.

Pricing model: price_new/price_old are carried 1:1. A future retail/wholesale
scheme is out of scope here (tracked with the multitenancy work).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("HHB_B2B")

# Fields enriched on existing rows via COALESCE(products.<f>, source.<f>):
# geometry + bearing specs + price + stock. Name/category/is_active are NOT
# touched on existing rows (we only enrich technical characteristics).
_ENRICH_FIELDS = [
    "weight", "d", "d_outer", "b_width",
    "rs_min", "static_load", "dynamic_load", "rpm_oil", "rpm_grease", "seal_type",
    "price_old", "price_new", "stock",
]


def _slugify(name: str) -> str:
    """Best-effort slug: lowercase, spaces→_, slashes→_."""
    return name.lower().strip().replace(" ", "_").replace("/", "_")


def _get_or_create_brand_ci(conn, name: str) -> int | None:
    """Case-insensitive get-or-create for brands. 'Kyk' matches 'KYK'."""
    if not name:
        return None
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM brands WHERE LOWER(name) = LOWER(%s)", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO brands (name, slug) VALUES (%s, %s) RETURNING id",
            (name, _slugify(name)),
        )
        brand_id = cur.fetchone()[0]
        conn.commit()
        return brand_id
    finally:
        cur.close()


def _get_or_create_category_ci(conn, name: str) -> int | None:
    """Case-insensitive get-or-create for categories."""
    if not name:
        return None
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(%s)", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO categories (name, slug) VALUES (%s, %s) RETURNING id",
            (name, _slugify(name)),
        )
        cat_id = cur.fetchone()[0]
        conn.commit()
        return cat_id
    finally:
        cur.close()


def import_from_kyk(conn) -> dict[str, Any]:
    """Transform rows from `kyk_products_import` staging into unified products.

    Returns: {"inserted": int, "enriched": int, "errors": int}.
    """
    stats: dict[str, Any] = {"inserted": 0, "enriched": 0, "errors": 0}

    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.kyk_products_import')")
    if cur.fetchone()[0] is None:
        cur.close()
        logger.warning("[import-kyk] kyk_products_import not found — nothing to import.")
        return stats

    cur.execute(
        """
        SELECT code, name, category, brand,
               weight, d, d_outer, b_width,
               rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
               price_old, price_new, stock, is_active,
               created_at, updated_at
        FROM kyk_products_import
        WHERE code IS NOT NULL
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    cur.close()

    for row in rows:
        (code, name, category, brand,
         weight, d, d_outer, b_width,
         rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
         price_old, price_new, stock, is_active,
         created_at, updated_at) = row
        try:
            brand_id = _get_or_create_brand_ci(conn, brand) if brand else None
            category_id = _get_or_create_category_ci(conn, category) if category else None

            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM products WHERE code = %s AND brand_id IS NOT DISTINCT FROM %s",
                (code, brand_id),
            )
            existing = cur.fetchone()

            if existing is None:
                # INSERT new product with all source fields.
                cur.execute(
                    """
                    INSERT INTO products
                        (code, name, brand_id, category_id,
                         weight, d, d_outer, b_width,
                         rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
                         price_old, price_new, stock, is_active, application,
                         created_at, updated_at)
                    VALUES (%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,
                            to_timestamp(%s), to_timestamp(%s))
                    """,
                    (code, name or code, brand_id, category_id,
                     weight, d, d_outer, b_width,
                     rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
                     price_old, price_new,
                     stock if stock is not None else 0,
                     True if is_active is None else is_active,
                     [],
                     created_at, updated_at),
                )
                conn.commit()
                cur.close()
                stats["inserted"] += 1
            else:
                # ENRICH: fill NULL characteristic/price/stock fields only.
                product_id = existing[0]
                set_clause = ", ".join(
                    f"{f} = COALESCE(products.{f}, %s)" for f in _ENRICH_FIELDS
                )
                cur.execute(
                    f"UPDATE products SET {set_clause}, updated_at = now() WHERE id = %s",
                    (weight, d, d_outer, b_width,
                     rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
                     price_old, price_new, stock, product_id),
                )
                conn.commit()
                cur.close()
                stats["enriched"] += 1
        except Exception as e:
            logger.error(f"[import-kyk] failed to import code={code!r}: {e}")
            stats["errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass

    logger.info(
        f"[import-kyk] done: inserted={stats['inserted']} enriched={stats['enriched']} "
        f"errors={stats['errors']}"
    )
    return stats


if __name__ == "__main__":
    import os
    import psycopg2
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [import-kyk] %(levelname)s %(message)s")
    load_dotenv("/var/www/crmks/backend/.env" if os.path.isdir("/var/www/crmks") else ".env", override=True)
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(dsn)
    try:
        stats = import_from_kyk(conn)
        print(stats)
    finally:
        conn.close()
```

- [ ] **Step 4: Прогнать тесты — должны пройти**

Run: `cd backend && python -m pytest tests/test_import_kyk_products.py -v`
Expected: 10 passed.

- [ ] **Step 5: Прогон ВЕСЬ набора — ничего не сломалось**

Run: `cd backend && python -m pytest -q`
Expected: 70 passed (60 + 10 новых).

- [ ] **Step 6: Коммит**

```bash
git add backend/scripts/import_kyk_products.py backend/tests/test_import_kyk_products.py
git commit -m "feat: import kyk.products with bearing-spec enrichment (case-insensitive brand)"
```

---

## Task 3: Деплой на прод — заливка staging, импорт, проверка, cleanup

**Files:** — (операционный task, выполняется на CRM-сервере `72.56.246.21`)

- [ ] **Step 1: Залить staging через delivery-скрипт**

На машине с SSH-доступом к сайт-серверу и psql-доступом к CRM (например, с CRM-сервера или локально):
```bash
bash deploy/import_kyk_products.sh
```
Expected в конце: `rows ≈ 735, active ≈ 85, with_price ≈ 85`.

Если `rows` сильно отличается от 735 — СТОП, разобраться, прежде чем идти дальше.

- [ ] **Step 2: Бэкап таблицы products перед импортом (страховка)**

На CRM-сервере:
```bash
CRM_DSN="$(grep '^DATABASE_URL=' /var/www/crmks/backend/.env | cut -d= -f2-)"
pg_dump "$CRM_DSN" --data-only --table=products > ~/products_backup_$(date +%Y%m%d_%H%M).sql
ls -la ~/products_backup_*.sql
```

- [ ] **Step 3: Запустить трансформер**

На CRM-сервере:
```bash
cd /var/www/crmks/backend
python -m scripts.import_kyk_products
```
Expected log: `[import-kyk] done: inserted=<N> enriched=<M> errors=0` и печать stats-dict.
- `inserted` ≈ число новых кодов (которых не было среди 478 sku_catalog KYK-записей).
- `enriched` ≈ число совпавших по `(code, brand=KYK)` — им добавились характеристики.
- `errors` **должен быть 0**. Если > 0 — посмотреть `api.log`, откатить бэкапом (Step 2), разобраться.

- [ ] **Step 4: Sanity-проверки в БД**

```bash
psql "$CRM_DSN" <<'SQL'
-- Всего товаров после импорта (было 478; должно быть больше, но не 478+735
-- из-за обогащения совпадающих KYK кодов).
SELECT count(*) AS total,
       count(*) FILTER (WHERE rs_min IS NOT NULL) AS with_rs_min,
       count(*) FILTER (WHERE dynamic_load IS NOT NULL) AS with_dynamic_load,
       count(*) FILTER (WHERE rpm_oil IS NOT NULL) AS with_rpm
FROM products;

-- Брендов по-прежнему 3 (KYK/FKD/HHB), без дубля 'Kyk'.
SELECT name FROM brands ORDER BY name;

-- Не должно быть дублей по (code, brand_id).
SELECT code, brand_id, count(*) FROM products GROUP BY code, brand_id HAVING count(*) > 1;
SQL
```
Expected: `with_rs_min`/`with_dynamic_load`/`with_rpm` заметно выросли (раньше у sku_catalog-записей характеристики были NULL); `brands` = 3 строки без `'Kyk'`; последний запрос — 0 строк.

- [ ] **Step 5: Проверить API v1 отдаёт обогащённые данные**

```bash
curl -s "http://72.56.246.21/api/v1/products?search=6203" | python -m json.tool | head -40
```
Expected: товар с заполненными `rs_min`, `static_load`, `dynamic_load`, `rpm_oil`, `rpm_grease`, `seal_type`, `weight`, `d`, `d_outer`, `b_width`.

- [ ] **Step 6: Удалить staging-таблицу (cleanup)**

```bash
psql "$CRM_DSN" -c "DROP TABLE kyk_products_import;"
```

- [ ] **Step 7: Обновить `docs/HANDOFF.md`**

В разделе «Что сделано» добавить пункт про импорт kyk, а в «Что осталось» вычеркнуть задачу #1. В «Known issues» обновить: обогащённые характеристики теперь есть у KYK-товаров; retail/wholesale-цены всё ещё отдельная задача.

```bash
git add docs/HANDOFF.md
git commit -m "docs: handoff — kyk.products imported (735), characteristics enriched"
```

---

## Self-Review (выполнено автором плана)

**1. Спека-покрытие:**
- Перенос 735 товаров → Task 0 (доставка) + Task 2 (трансформер). ✓
- Обогащение характеристик (`rs_min`/`load`/`rpm`) для существующих → Task 2, `test_import_enriches_existing_without_overwriting`. ✓
- Все 735, сохранить `is_active` → Task 2, `test_import_preserves_is_active`. ✓
- Цены 1:1 → Task 2, `test_import_preserves_prices_and_stock`. ✓
- Case-insensitive brand ('Kyk'→'KYK') → Task 2, `test_import_resolves_brand_case_insensitive`. ✓
- Timestamp-конверсия → Task 2, `test_import_converts_unix_timestamps`. ✓
- Идемпотентность → Task 2, `test_import_is_idempotent`. ✓
- Guard на отсутствие staging → Task 2, `test_import_no_staging_returns_empty`. ✓
- Пропуск NULL-code → Task 2, `test_import_skips_rows_without_code`. ✓
- Деплой + sanity + бэкап + cleanup → Task 3. ✓

**2. Placeholder scan:** нет TBD/TODO; все SQL/Python-блоки — финальный код; команды — конкретные.

**3. Type consistency:** `import_from_kyk(conn)` → используется в тестах и `__main__`; `_get_or_create_brand_ci`/`_get_or_create_category_ci` — единообразно; статсы `{inserted, enriched, errors}` едины во всех местах; `_ENRICH_FIELDS` совпадает по составу в INSERT-значениях и UPDATE-COALESCE.

**Замеченные риски (явно для исполнителя):**
- В kyk `is_active` nullable; для новых INSERT'ов NULL → `true` (см. `True if is_active is None`). Это сознательное решение (новый товар видим по умолчанию); для 650 скрытых источник уже даёт `false`.
- Имя продукта у существующих строк НЕ обновляется при enrich (только характеристики) — соответствует «не затирать».
- `category_id`/`is_active` у существующих строк НЕ трогаются при enrich — только характеристики/цены/stock.
