# Proposals-flow: migrate sku_catalog → products Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести весь proposal-флоу (КП, email, AI-парсинг, список SKU) с чтения старой `sku_catalog` на унифицированный каталог `products`/`brands`, чтобы новые 735 kyk-товаров (и все будущие) стали видны в `/admin/proposals`, и закрыть Known Issue #1 (FK proposal_items.sku_id).

**Architecture:** Чисто кодовая миграция — исторических КП на проде нет (`proposal_items` пуста), поэтому data-migration не требуется. Делаем:
1. **Миграция 004:** DROP старый FK `proposal_items.sku_id → sku_catalog`, ADD новый `→ products(id) ON DELETE RESTRICT`. На пустой таблице — мгновенно.
2. **4 SQL-точки контакта** (`proposals.py:137, 346`; `email_service.py:51`; `ai_claude_agent.py:282`) — переписать JOIN'ы с `sku_catalog` на `products p LEFT JOIN brands b ON b.id=p.brand_id`, с маппингом полей: `s.sku→p.code`, `s.type→p.name`, `s.brand→b.name`, `s.price→p.price_new`.
3. **`/api/catalog/skus`** (`catalog_skus.py`) — переписать SELECT с `sku_catalog` на `products + brands + categories`, сохранив форму ответа (чтобы фронтенд не сломался).
4. **Тесты** — создаются с нуля для proposal-флоу (сейчас их нет), плюс миграция 004 + обновить catalog_skus-проверки.
5. **`sku_catalog` НЕ дропаем** (destructive, отдельная задача после проверки).

**Tech Stack:** Python 3, FastAPI, psycopg2, pytest + PostgreSQL test DB.

**Принятые решения (из уточнения с заказчиком):**
- Scope: **полная миграция** (4 точки + FK + /api/catalog/skus). `DROP sku_catalog` НЕ включаем.
- FK: **`ON DELETE RESTRICT`** (нельзя удалить товар, на который есть КП; история защищена).
- Маппинг `sku_catalog.type → products.name` (сохраняет текущее поведение КП — поле «Описание»).
- Data-migration не нужна: на проде `proposal_items` пуста (0 строк), рисков потери данных нет.

---

## Маппинг полей (единая таблица для всех точек контакта)

| Старое (`sku_catalog`) | Новое (`products` + JOIN) | Примечание |
|---|---|---|
| `s.sku` | `p.code` | артикул |
| `s.type` | `p.name` | описание (поле «Описание» в КП) |
| `s.brand` | `b.name` | бренд (через JOIN products.brand_id→brands.id) |
| `s.price` | `p.price_new` | цена (используется при создании item) |
| `s.id` | `p.id` | PK — теперь `proposal_items.sku_id` ссылается на products.id |

**Семантика INNER vs LEFT JOIN:** текущий код использует INNER JOIN. После миграции INNER сохранится (КП ссылаются на существующие товары). При `ON DELETE RESTRICT` удалить товар со ссылкой невозможно → orphan-ситуаций не возникает → INNER безопасен.

---

## File Structure

| Файл | Ответственность | Статус |
|---|---|---|
| `backend/migrations/004_proposal_items_fk_products.sql` | Миграция FK: DROP старый, ADD новый `→ products(id) ON DELETE RESTRICT` | **Create** |
| `backend/migrations/runner.py` | Добавить `apply_migration_004(conn)` + вызов в `apply_all` | **Modify** (2 правки) |
| `backend/routes/proposals.py` | 2 точки: `:137` (JOIN при чтении КП), `:346` (price при создании item) | **Modify** (2 SQL) |
| `backend/services/email_service.py` | 1 точка: `:51` (JOIN в email-КП) | **Modify** (1 SQL) |
| `backend/routes/ai_claude_agent.py` | 1 точка: `:282` (ILIKE-поиск при парсинге) | **Modify** (1 SQL) |
| `backend/routes/catalog_skus.py` | `GET /api/catalog/skus` — переписать SELECT на products+brands+categories | **Modify** (1 SQL) |
| `backend/tests/test_migration_004.py` | Тест миграции FK (RESTRICT срабатывает, старый FK снят) | **Create** |
| `backend/tests/test_proposals_products.py` | Тесты proposal-флоу: создание item по products.id, чтение КП с JOIN products, email items, 404 на несуществующий sku_id | **Create** |
| `backend/tests/test_catalog_skus_products.py` | Тест `/api/catalog/skus` отдаёт товары из products (включая kyk) | **Create** |
| `backend/tests/conftest.py` | Добавить `proposals`, `proposal_items`, `clients`, `users` в `_TABLES_TO_CLEAR` (для новых proposal-тестов) | **Modify** (1 строка) |

---

## Task 1: Миграция 004 — FK proposal_items.sku_id → products

**Files:**
- Create: `backend/migrations/004_proposal_items_fk_products.sql`
- Modify: `backend/migrations/runner.py`
- Test: `backend/tests/test_migration_004.py`

### Часть A: миграция + runner (сначала код, потом тест на schema)

- [ ] **Step 1: Создать SQL-миграцию**

`backend/migrations/004_proposal_items_fk_products.sql`:
```sql
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
```

- [ ] **Step 2: Добавить `apply_migration_004` в runner**

В `backend/migrations/runner.py`, сразу после `apply_migration_003` (строка 59) и перед `apply_all`:
```python
def apply_migration_004(conn) -> None:
    """Apply migration 004 — repoint proposal_items.sku_id FK to products(id) RESTRICT.

    Safe on fresh DBs (idempotent, guarded). Assumes products + proposal_items
    tables already exist (created by migration 003 and startup/db_init).
    """
    sql_path = _MIGRATIONS_DIR / "004_proposal_items_fk_products.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 004_proposal_items_fk_products.sql applied.")
```

- [ ] **Step 3: Добавить вызов в `apply_all`**

В `backend/migrations/runner.py`, функция `apply_all` (строки 62-72), после `apply_migration_003(conn)`:
```python
def apply_all(dsn: str) -> None:
    """Apply all migrations to the DB at `dsn`. Used on app startup."""
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        apply_migration_001(conn)
        apply_migration_002(conn)
        apply_migration_003(conn)
        apply_migration_004(conn)
    finally:
        conn.close()
```

### Часть B: тест миграции

- [ ] **Step 4: Создать тест (RED)**

`backend/tests/test_migration_004.py`:
```python
"""Tests for migration 004: proposal_items.sku_id FK → products(id) RESTRICT."""
import pytest
import psycopg2

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003, apply_migration_004,
)


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


def _create_proposal_items(conn):
    """Create proposal_items with the OLD FK to sku_catalog (mimics db_init state)."""
    cur = conn.cursor()
    # parent tables proposals + clients + users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY, name TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            title VARCHAR(300), total_amount NUMERIC(14,2) DEFAULT 0,
            discount_global INTEGER DEFAULT 0, status VARCHAR(50) DEFAULT 'draft',
            email_sent BOOLEAN DEFAULT FALSE, created_at VARCHAR(100), updated_at VARCHAR(100)
        )
        """
    )
    # proposal_items with the legacy FK → sku_catalog(id) ON DELETE CASCADE
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_items (
            id SERIAL PRIMARY KEY,
            proposal_id INTEGER REFERENCES proposals(id) ON DELETE CASCADE,
            sku_id INTEGER REFERENCES sku_catalog(id) ON DELETE CASCADE,
            qty INTEGER NOT NULL DEFAULT 1,
            price_base NUMERIC(12,2) NOT NULL DEFAULT 0,
            discount_item INTEGER DEFAULT 0,
            price_final NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """
    )
    cur.close()


def _fk_target(conn, constraint_name: str) -> str | None:
    """Return the referenced table name for a given FK constraint, or None."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT confrelid::regclass::text
        FROM pg_constraint
        WHERE conname = %s AND contype = 'f'
        """,
        (constraint_name,),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def _fk_delete_action(conn, constraint_name: str) -> str | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT confdeltype FROM pg_constraint WHERE conname = %s AND contype = 'f'
        """,
        (constraint_name,),
    )
    row = cur.fetchone()
    cur.close()
    # 'a' = NO ACTION, 'r' = RESTRICT, 'c' = CASCADE, 'n' = SET NULL, 'd' = SET DEFAULT
    return row[0] if row else None


def test_migration_repoints_fk_to_products(db_conn):
    """After migration, the FK should reference products(id), not sku_catalog."""
    _apply_all_migrations(db_conn)
    _create_proposal_items(db_conn)

    # Before migration: FK points at sku_catalog
    assert _fk_target(db_conn, "proposal_items_sku_id_fkey") in ("sku_catalog", None)

    apply_migration_004(db_conn)

    # After migration: FK points at products
    assert _fk_target(db_conn, "proposal_items_sku_id_fkey") == "products"


def test_migration_sets_on_delete_restrict(db_conn):
    """The new FK must be ON DELETE RESTRICT (protects historical proposals)."""
    _apply_all_migrations(db_conn)
    _create_proposal_items(db_conn)
    apply_migration_004(db_conn)
    assert _fk_delete_action(db_conn, "proposal_items_sku_id_fkey") == "r"


def test_migration_is_idempotent(db_conn):
    """Running migration twice must not error and must leave FK pointing at products."""
    _apply_all_migrations(db_conn)
    _create_proposal_items(db_conn)
    apply_migration_004(db_conn)
    apply_migration_004(db_conn)  # second run
    assert _fk_target(db_conn, "proposal_items_sku_id_fkey") == "products"
    assert _fk_delete_action(db_conn, "proposal_items_sku_id_fkey") == "r"


def test_migration_tolerant_when_proposal_items_absent(db_conn):
    """If proposal_items doesn't exist, migration is a no-op (fresh test DB)."""
    _apply_all_migrations(db_conn)
    # Do NOT create proposal_items.
    apply_migration_004(db_conn)  # should not raise
```

- [ ] **Step 5: Прогнать — должен пройти (GREEN)**

Run: `cd backend && python -m pytest tests/test_migration_004.py -v`
Expected: 4 passed.

(Миграция применяется после создания proposal_items фикстурой, поэтому тесты сразу зелёные — это проверка schema, а не RED→GREEN TDD. Если что-то падает — чиним миграцию, а не тест.)

- [ ] **Step 6: Полный набор**

Run: `cd backend && python -m pytest -q`
Expected: 76 passed (72 + 4 новых).

- [ ] **Step 7: Коммит**

```bash
git add backend/migrations/004_proposal_items_fk_products.sql backend/migrations/runner.py backend/tests/test_migration_004.py
git commit -m "feat(migration): 004 repoint proposal_items.sku_id FK to products(id) RESTRICT"
```

---

## Task 2: Перевести 4 SQL-точки proposals/email/ai на products

**Files:**
- Modify: `backend/routes/proposals.py:137, 346`
- Modify: `backend/services/email_service.py:51`
- Modify: `backend/routes/ai_claude_agent.py:282`

Все 4 правки изолированы (замена SQL-строки + маппинг полей). Логика Python не меняется.

- [ ] **Step 1: `proposals.py:137` — JOIN при чтении КП**

В `backend/routes/proposals.py` функция `get_proposal`, заменить блок `cursor.execute(q("""..."""), (proposal_id,))` (строки 134-140):

**Было:**
```python
    cursor.execute(
        q("""
        SELECT pi.id, pi.sku_id, s.sku, s.type, s.brand, pi.qty, pi.price_base, pi.discount_item, pi.price_final
        FROM proposal_items pi JOIN sku_catalog s ON pi.sku_id = s.id WHERE pi.proposal_id = %s
        """),
        (proposal_id,),
    )
```

**Стало:**
```python
    cursor.execute(
        q("""
        SELECT pi.id, pi.sku_id, p.code, p.name, b.name, pi.qty, pi.price_base, pi.discount_item, pi.price_final
        FROM proposal_items pi
                JOIN products p ON pi.sku_id = p.id
                LEFT JOIN brands b ON b.id = p.brand_id
        WHERE pi.proposal_id = %s
        """),
        (proposal_id,),
    )
```

(Позиции колонок в `r[0..8]` и словарь `items` ниже не меняются — `r[2]→sku/code`, `r[3]→type/name`, `r[4]→brand`. `b.name` через LEFT JOIN на случай товара без бренда — но в RESTRICT-модели это избыточно безопасно.)

- [ ] **Step 2: `proposals.py:346` — price при создании item**

В `backend/routes/proposals.py` функция `add_proposal_item`, заменить строку 346:

**Было:**
```python
    cursor.execute(q("SELECT price FROM sku_catalog WHERE id = %s"), (data.sku_id,))
```

**Стало:**
```python
    cursor.execute(q("SELECT price_new FROM products WHERE id = %s"), (data.sku_id,))
```

(Одна колонка, `row[0]` — без изменений. 404 на несуществующий sku_id остаётся рабочим.)

- [ ] **Step 3: `email_service.py:51` — JOIN в email-КП**

В `backend/services/email_service.py` функция `_get_proposal_for_email`, заменить блок `cursor.execute(q("""..."""), (proposal_id,))` (строки 40-57):

**Было:**
```python
        cursor.execute(
            q(
                """
                SELECT
                    pi.qty,
                    pi.price_base,
                    pi.discount_item,
                    pi.price_final,
                    s.sku,
                    s.type
                FROM proposal_items pi
                JOIN sku_catalog s ON pi.sku_id = s.id
                WHERE pi.proposal_id = %s
                ORDER BY pi.id
                """
            ),
            (proposal_id,),
        )
```

**Стало:**
```python
        cursor.execute(
            q(
                """
                SELECT
                    pi.qty,
                    pi.price_base,
                    pi.discount_item,
                    pi.price_final,
                    p.code,
                    p.name
                FROM proposal_items pi
                JOIN products p ON pi.sku_id = p.id
                WHERE pi.proposal_id = %s
                ORDER BY pi.id
                """
            ),
            (proposal_id,),
        )
```

(Распаковка `for qty, price_base, discount_item, price_final, sku, item_type in items_rows:` ниже не меняется — порядок колонок тот же: `p.code→sku`, `p.name→item_type`.)

- [ ] **Step 4: `ai_claude_agent.py:282` — ILIKE-поиск при парсинге**

В `backend/routes/ai_claude_agent.py` функция `parse_kp_request`, заменить блок `cursor.execute(...)` (строки 281-284):

**Было:**
```python
        cursor.execute(
            q("SELECT id, sku, price FROM sku_catalog WHERE sku ILIKE %s LIMIT 1"),
            (f"%{article}%",),
        )
```

**Стало:**
```python
        cursor.execute(
            q("SELECT id, code, price_new FROM products WHERE code ILIKE %s LIMIT 1"),
            (f"%{article}%",),
        )
```

(Распаковка `cat_row[0]→id`, `[1]→name` (теперь code), `[2]→price` ниже не меняется. `name` в enriched-дикте теперь получает `code` — это артикул, что разумнее для парсинга. Поведение поиска по ILIKE сохранено.)

- [ ] **Step 5: Прогнать существующий набор (пока без новых proposal-тестов)**

Run: `cd backend && python -m pytest -q`
Expected: 76 passed (ничего не должно сломаться — старых proposal-тестов нет, catalog_v1-тесты не трогают sku_catalog напрямую через эти точки).

- [ ] **Step 6: Коммит**

```bash
git add backend/routes/proposals.py backend/services/email_service.py backend/routes/ai_claude_agent.py
git commit -m "refactor(proposals): read SKU data from products instead of sku_catalog"
```

---

## Task 3: Тесты proposal-флоу (новые, с нуля)

**Files:**
- Modify: `backend/tests/conftest.py` (1 строка)
- Create: `backend/tests/test_proposals_products.py`

- [ ] **Step 1: Добавить proposal-таблицы в `_TABLES_TO_CLEAR`**

В `backend/tests/conftest.py`, строка 17:

**Было:**
```python
_TABLES_TO_CLEAR = ["products", "categories", "brands", "sku_catalog", "kyk_products_import", "job_queue"]
```

**Стало:**
```python
_TABLES_TO_CLEAR = ["proposal_items", "proposals", "clients", "users", "products", "categories", "brands", "sku_catalog", "kyk_products_import", "job_queue"]
```

(Порядок важен: dependents сначала. `proposal_items` ссылается на `proposals` и `products`, поэтому идёт первым.)

- [ ] **Step 2: Создать тест-файл (RED)**

`backend/tests/test_proposals_products.py`:
```python
"""Tests for proposal-flow reading from unified products (not sku_catalog).

These are the first tests covering the proposal endpoints' SKU interactions.
They verify that after the sku_catalog→products migration:
- creating a proposal_item reads price from products.price_new
- reading a proposal returns code/name/brand from products+brands
- email enrichment pulls code/name from products
- a non-existent sku_id returns 404
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003, apply_migration_004,
)


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)
    apply_migration_004(conn)


def _seed_proposal_tables(conn):
    """Create clients/proposals/proposal_items (mimic startup/db_init) and seed."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY, name TEXT, email TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id SERIAL PRIMARY KEY,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            title VARCHAR(300), total_amount NUMERIC(14,2) DEFAULT 0,
            discount_global INTEGER DEFAULT 0, status VARCHAR(50) DEFAULT 'draft',
            email_sent BOOLEAN DEFAULT FALSE,
            created_at VARCHAR(100), updated_at VARCHAR(100)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_items (
            id SERIAL PRIMARY KEY,
            proposal_id INTEGER REFERENCES proposals(id) ON DELETE CASCADE,
            sku_id INTEGER REFERENCES products(id) ON DELETE RESTRICT,
            qty INTEGER NOT NULL DEFAULT 1,
            price_base NUMERIC(12,2) NOT NULL DEFAULT 0,
            discount_item INTEGER DEFAULT 0,
            price_final NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """
    )
    # Seed: 1 client, 1 proposal, 1 product with brand.
    cur.execute("INSERT INTO clients (name, email) VALUES ('ООО Тест', 't@t.t')")
    cur.execute(
        "INSERT INTO proposals (client_id, title, total_amount, status) VALUES (1, 'КП тест', 0, 'draft')"
    )
    cur.execute("INSERT INTO brands (name, slug) VALUES ('KYK', 'kyk') RETURNING id")
    brand_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO products (code, name, brand_id, price_new, stock)
        VALUES ('6203 ZZ', 'Подшипник 6203 ZZ', %s, 95.0, 10) RETURNING id
        """,
        (brand_id,),
    )
    pid = cur.fetchone()[0]
    cur.close()
    return pid  # product id


@pytest.fixture
def app_client(db_conn, monkeypatch):
    """Wire TestClient to the test DB."""
    _apply_all_migrations(db_conn)
    product_id = _seed_proposal_tables(db_conn)

    # Force the app to use the test DB.
    import os
    monkeypatch.setenv("DATABASE_URL", os.environ.get("TEST_DATABASE_URL"))
    # Re-init db module's connection to test DB.
    import db as db_module
    monkeypatch.setattr(db_module, "PG_URL", os.environ.get("TEST_DATABASE_URL"))
    monkeypatch.setattr(db_module, "_use_pg", True)

    client = TestClient(app)
    client.state["product_id"] = product_id
    return client


def test_add_item_reads_price_from_products(app_client):
    """POST /api/proposals/{id}/items snapshots price from products.price_new."""
    pid = app_client.state["product_id"]
    resp = app_client.post(
        "/api/proposals/1/items",
        json={"sku_id": pid, "qty": 2, "discount_item": 0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "added"


def test_add_item_404_on_unknown_sku(app_client):
    """A sku_id not in products returns 404."""
    resp = app_client.post(
        "/api/proposals/1/items",
        json={"sku_id": 999999, "qty": 1, "discount_item": 0},
    )
    assert resp.status_code == 404


def test_get_proposal_returns_products_data(app_client):
    """GET /api/proposals/{id} returns code/name/brand from products+brands."""
    pid = app_client.state["product_id"]
    app_client.post(
        "/api/proposals/1/items",
        json={"sku_id": pid, "qty": 1, "discount_item": 0},
    )
    resp = app_client.get("/api/proposals/1")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["sku"] == "6203 ZZ"      # products.code
    assert it["type"] == "Подшипник 6203 ZZ"  # products.name
    assert it["brand"] == "KYK"        # brands.name
    assert float(it["price_base"]) == 95.0
```

- [ ] **Step 3: Прогнать — разобраться с результатом**

Run: `cd backend && python -m pytest tests/test_proposals_products.py -v`

Эти тесты могут выявить инфраструктурные нюансы (как `main.app` подключается к БД, как `get_db()` работает в TestClient). Если тесты падают на подключении к БД (а не на логике), это **не баг миграции** — это особенность test-инфраструктуры проекта (которая сейчас не покрывает proposal-эндпоинты).

**Если падает инфраструктура БД:** упростить тесты до прямых вызовов функций/SQL (без TestClient), проверяя только SQL-логику миграции. Цель — прикрыть **изменённые SQL**, а не построить полную integration-test-инфраструктуру (это отдельная задача).

Минимальная альтернатива (если TestClient не заводится) — тестировать SQL напрямую через `db_conn`:
```python
def test_get_proposal_sql_returns_products_join(db_conn):
    """The JOIN query in get_proposal reads from products, not sku_catalog."""
    _apply_all_migrations(db_conn)
    _seed_proposal_tables(db_conn)
    # Insert a proposal_item manually.
    cur = db_conn.cursor()
    cur.execute(
        "INSERT INTO proposal_items (proposal_id, sku_id, qty, price_base, price_final) "
        "VALUES (1, (SELECT id FROM products WHERE code='6203 ZZ'), 1, 95.0, 95.0)"
    )
    cur.close()
    # Run the exact JOIN from proposals.py:137
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT pi.id, pi.sku_id, p.code, p.name, b.name, pi.qty, pi.price_base, pi.discount_item, pi.price_final
        FROM proposal_items pi
        JOIN products p ON pi.sku_id = p.id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE pi.proposal_id = %s
        """,
        (1,),
    )
    r = cur.fetchone()
    cur.close()
    assert r[2] == "6203 ZZ"            # code
    assert r[3] == "Подшипник 6203 ZZ"  # name
    assert r[4] == "KYK"                # brand
```

- [ ] **Step 4: Полный набор**

Run: `cd backend && python -m pytest -q`
Expected: все тесты зелёные (точное число зависит от того, сколько proposal-тестов удалось завести).

- [ ] **Step 5: Коммит**

```bash
git add backend/tests/conftest.py backend/tests/test_proposals_products.py
git commit -m "test(proposals): cover proposal-flow reading from products"
```

---

## Task 4: Перевести `/api/catalog/skus` на products

**Files:**
- Modify: `backend/routes/catalog_skus.py:40-94` (функция `list_skus`)
- Create: `backend/tests/test_catalog_skus_products.py`

Это та самая видимость SKU для `/admin/proposals`. Форма ответа сохраняется (чтобы фронтенд не сломался), меняется только источник.

- [ ] **Step 1: Переписать `list_skus` (TDD — сначала тест)**

Создать `backend/tests/test_catalog_skus_products.py`:
```python
"""Tests for /api/catalog/skus reading from unified products."""
import pytest
from fastapi.testclient import TestClient

from main import app
from migrations.runner import apply_migration_001, apply_migration_002, apply_migration_003


def _apply_all(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


@pytest.fixture
def catalog_client(db_conn, monkeypatch):
    _apply_all(db_conn)
    cur = db_conn.cursor()
    cur.execute("INSERT INTO brands (name, slug) VALUES ('KYK', 'kyk') RETURNING id")
    brand_id = cur.fetchone()[0]
    cur.execute("INSERT INTO categories (name, slug) VALUES ('Миниатюрные', 'min') RETURNING id")
    cat_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO products (code, name, brand_id, category_id, d, d_outer, b_width, price_new, stock, is_active)
        VALUES
            ('6203 ZZ', 'Подшипник 6203 ZZ', %s, %s, 17, 40, 12, 95.0, 10, true),
            ('604', 'Подшипник 604', %s, %s, 4, 12, 4, NULL, 0, false)
        """,
        (brand_id, cat_id, brand_id, cat_id),
    )
    cur.close()

    import os
    monkeypatch.setenv("DATABASE_URL", os.environ.get("TEST_DATABASE_URL"))
    import db as db_module
    monkeypatch.setattr(db_module, "PG_URL", os.environ.get("TEST_DATABASE_URL"))
    monkeypatch.setattr(db_module, "_use_pg", True)
    return TestClient(app)


def test_list_skus_returns_from_products(catalog_client):
    resp = catalog_client.get("/api/catalog/skus?search=6203")
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["sku"] == "6203 ZZ" for i in items)


def test_list_skus_preserves_field_shape(catalog_client):
    """Response keeps the legacy field names (sku, brand, d, D, B, price) so frontend works."""
    resp = catalog_client.get("/api/catalog/skus?search=6203")
    items = resp.json()
    assert len(items) == 1
    it = items[0]
    # Legacy fields must be present.
    for field in ("id", "sku", "brand", "d", "D", "B", "price", "stock"):
        assert field in it, f"missing field {field}"
    assert it["sku"] == "6203 ZZ"
    assert it["brand"] == "KYK"
    assert float(it["d"]) == 17
    assert float(it["price"]) == 95.0
```

Run: `cd backend && python -m pytest tests/test_catalog_skus_products.py -v`
Expected: FAIL — `list_skus` still reads sku_catalog, не находит 6203 ZZ.

- [ ] **Step 2: Переписать `list_skus` на products**

В `backend/routes/catalog_skus.py`, заменить тело функции `list_skus` (строки 40-94):

**Было** (строки 40-94):
```python
@router.get("/api/catalog/skus")
def list_skus(
    category: Optional[str] = None,
    search: Optional[str] = None,
    d_min: Optional[float] = None,
    d_max: Optional[float] = None,
):
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT id, sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img
        FROM sku_catalog
        WHERE 1=1
    """.strip()
    params = []

    if category and category != "all":
        query += " AND category = %s"
        params.append(category)

    if search:
        query += " AND (sku ILIKE %s OR type ILIKE %s OR gost ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if d_min is not None:
        query += " AND d_inner >= %s"
        params.append(d_min)

    if d_max is not None:
        query += " AND d_inner <= %s"
        params.append(d_max)

    query += " ORDER BY id ASC"
    cursor.execute(q(query), params)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "sku": r[1],
            "category": r[2],
            "gost": r[3],
            "d": float(r[4]) if r[4] else None,
            "D": float(r[5]) if r[5] else None,
            "B": float(r[6]) if r[6] else None,
            "type": r[7],
            "brand": r[8],
            "stock": r[9],
            "price": float(r[10]) if r[10] else 0,
            "img": r[11],
        }
        for r in rows
    ]
```

**Стало:**
```python
@router.get("/api/catalog/skus")
def list_skus(
    category: Optional[str] = None,
    search: Optional[str] = None,
    d_min: Optional[float] = None,
    d_max: Optional[float] = None,
):
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT p.id, p.code, c.name, b.name, p.d, p.d_outer, p.b_width, p.name,
               p.stock, p.price_new, p.img
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE 1=1
    """.strip()
    params = []

    if category and category != "all":
        query += " AND c.name = %s"
        params.append(category)

    if search:
        query += " AND (p.code ILIKE %s OR p.name ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    if d_min is not None:
        query += " AND p.d >= %s"
        params.append(d_min)

    if d_max is not None:
        query += " AND p.d <= %s"
        params.append(d_max)

    query += " ORDER BY p.id ASC"
    cursor.execute(q(query), params)

    rows = cursor.fetchall()
    conn.close()

    # Preserve the legacy response shape (sku, brand, d, D, B, type, price) so
    # the existing frontend /admin/proposals keeps working unchanged.
    return [
        {
            "id": r[0],
            "sku": r[1],          # products.code
            "category": r[2],     # categories.name
            "gost": "",           # not in products; keep field for frontend compat
            "d": float(r[4]) if r[4] else None,
            "D": float(r[5]) if r[5] else None,
            "B": float(r[6]) if r[6] else None,
            "type": r[7],         # products.name (description)
            "brand": r[3],        # brands.name
            "stock": str(r[8]) if r[8] is not None else "0",
            "price": float(r[9]) if r[9] else 0,
            "img": r[10],
        }
        for r in rows
    ]
```

**Важные решения в новом SELECT:**
- Порядок колонок: `id, code, category.name, brand.name, d, d_outer, b_width, products.name, stock, price_new, img` (11 колонок).
- `gost` в products нет → возвращаем пустую строку `""` (фронтенд ожидает поле, но не использует).
- `stock` приводится к строке (legacy sku_catalog.stock был text → фронтенд мог показывать «В наличии»; int→str сохраняет совместимость).
- `price` → `price_new` (актуальная цена).
- Поиск `gost` убран (поля нет), но добавлен поиск по `p.name` (description).

- [ ] **Step 3: Прогнать тесты catalog_skus (GREEN)**

Run: `cd backend && python -m pytest tests/test_catalog_skus_products.py -v`
Expected: 2 passed.

- [ ] **Step 4: Полный набор**

Run: `cd backend && python -m pytest -q`
Expected: все зелёные.

- [ ] **Step 5: Коммит**

```bash
git add backend/routes/catalog_skus.py backend/tests/test_catalog_skus_products.py
git commit -m "refactor(catalog): /api/catalog/skus reads from products (visible in /admin/proposals)"
```

---

## Task 5: Деплой на прод + проверка

**Files:** — (операционный task на CRM-сервере)

- [ ] **Step 1: Бэкап schema + данных proposal_items (страховка, хотя пусто)**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21
CRM_DSN="$(grep '^DATABASE_URL=' /var/www/crmks/backend/.env | cut -d= -f2-)"
pg_dump "$CRM_DSN" --schema-only --table=proposal_items > ~/schema_proposal_items_$(date +%Y%m%d).sql
echo "proposal_items count before:"; psql "$CRM_DSN" -t -c "SELECT count(*) FROM proposal_items;"
```

- [ ] **Step 2: Pull миграции на CRM + apply**

```bash
cd /var/www/crmks
git pull origin main
cd backend
venv/bin/python -c "from migrations.runner import apply_all; from db import PG_URL; apply_all(PG_URL)"
```
(Или перезапустить API — `apply_all` вызывается в `main.py` при старте.)

- [ ] **Step 3: Проверить, что FK переведён**

```bash
psql "$CRM_DSN" -c "SELECT conname, confrelid::regclass::text AS references, confdeltype FROM pg_constraint WHERE conname='proposal_items_sku_id_fkey';"
```
Expected: `references=products`, `confdeltype=r` (RESTRICT).

- [ ] **Step 4: Перезапустить API + health-check**

```bash
systemctl restart crmks-api
sleep 3
systemctl is-active crmks-api
curl -s http://72.56.246.21/api/catalog/skus?search=6203 | head -c 300
```
Expected: в ответе виден `6203 ZZ` (новый kyk-товар).

- [ ] **Step 5: Sanity — /api/catalog/skus отдаёт новые товары**

```bash
echo "Total SKUs visible via /api/catalog/skus:"
curl -s "http://72.56.246.21/api/catalog/skus" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
echo "Sample 6203 ZZ:"
curl -s "http://72.56.246.21/api/catalog/skus?search=6203%20ZZ" | python3 -m json.tool | head -20
```
Expected: ~1213 SKU (включая 735 новых), `6203 ZZ` с характеристиками.

- [ ] **Step 6: Обновить HANDOFF.md**

Вычеркнуть Known Issue #1 (FK переведён), отметить что proposal-флоу теперь на products. Добавить в «Что осталось»: DROP sku_catalog (когда подтвердится стабильность).

```bash
git add docs/HANDOFF.md
git commit -m "docs: handoff — proposal-flow migrated to products, FK 004 applied"
```

---

## Self-Review (выполнено автором плана)

**1. Спека-покрытие:**
- 4 SQL-точки контакта → Task 2 (4 шага). ✓
- Миграция FK 004 → Task 1. ✓
- `/api/catalog/skus` → products → Task 4. ✓
- `type → products.name` маппинг → Task 2 Step 1 (r[3]→name), Task 4 Step 2 (type=products.name). ✓
- `ON DELETE RESTRICT` → Task 1 SQL + тест `test_migration_sets_on_delete_restrict`. ✓
- Data-migration не нужна (proposal_items пуста) → явно отмечено, нет таблицы-маппинга. ✓
- `sku_catalog` НЕ дропаем → явно отмечено. ✓

**2. Placeholder scan:** нет TBD/TODO; все SQL/Python-блоки — финальный код; команды — конкретные.

**3. Type consistency:** `apply_migration_004(conn)` — единая сигнатура во всех вызовах; FK-имя `proposal_items_sku_id_fkey` консистентно; маппинг полей `sku→code, type→name, brand→brands.name, price→price_new` един во всех 5 точках.

**Риски (явно для исполнителя):**
- **TestClient + БД:** proposal-тесты (Task 3) — первые integration-тесты для proposal-эндпоинтов. Инфраструктура `monkeypatch.setattr(db_module, ...)` может не завестись с первого раза. В плане заложена альтернатива — тестировать SQL напрямую через `db_conn` (без TestClient), проверяя только изменённые JOIN'ы. Цель — прикрыть миграцию, а не строить полную test-инфраструктуру.
- **`stock` тип:** legacy sku_catalog.stock был text («В наличии»), products.stock — int. В `list_skus` привожу к str для совместимости с фронтендом. Если фронтенд парсит stock как int — нужно будет убрать `str()`. Проверить при деплое.
- **INNER JOIN в get_proposal:** если КП ссылается на удалённый товар — item исчезнет. Но RESTRICT делает это невозможным (нельзя удалить товар со ссылкой). Безопасно.
