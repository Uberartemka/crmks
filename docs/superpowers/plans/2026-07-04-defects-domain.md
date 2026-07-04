# Defects Domain + users.client_id Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить backend для дефектовки (таблица `defects` + CRUD `/api/defects`) + предварительную миграцию `users.client_id` (фундамент для всех доменов Группы C). Заменить захардкоженный `client/DefectsView.vue` на реальные данные.

**Architecture:** Следовать эталону `notes`: router → service → db, `Depends(get_current_user())`, dual-dialect PG+SQLite через `q()`. Сначала миграция `users.client_id` (Task 1) + обновление auth_deps (Task 2), потом таблица `defects` + миграция (Task 3), CRUD backend + тесты (Task 4-5), frontend api/store/types (Task 6), переработка DefectsView (Task 7).

**Tech Stack:** Python 3 (FastAPI, psycopg2), Vue 3 + TypeScript + Pinia, pytest, Tailwind.

**Spec:** `docs/superpowers/specs/2026-07-04-defects-domain-design.md`.

---

## File Structure

| Файл | Ответственность | Статус |
|---|---|---|
| `backend/migrations/005_users_client_id.sql` | ALTER users ADD client_id (PG idempotent) | Create |
| `backend/migrations/006_defects.sql` | CREATE TABLE defects (PG idempotent) | Create |
| `backend/migrations/runner.py` | apply_migration_005, apply_migration_006 + apply_all | Modify |
| `backend/startup/db_init.py` | client_id + defects table в обоих блоках | Modify |
| `backend/auth_deps.py` | get_current_user возвращает client_id | Modify |
| `backend/schemas/defects.py` | DefectCreate, DefectUpdate | Create |
| `backend/services/defects_service.py` | CRUD + owner-check | Create |
| `backend/routes/defects.py` | /api/defects эндпоинты | Create |
| `backend/routes/index.py` | регистрация defects_router | Modify |
| `backend/tests/test_migration_005_006.py` | тест миграций | Create |
| `backend/tests/test_defects_crud.py` | тесты CRUD + owner-check | Create |
| `src/types/defect.ts` | TS типы | Create |
| `src/api/defects.ts` | defectsApi | Create |
| `src/stores/defects.ts` | Pinia store | Create |
| `src/views/client/DefectsView.vue` | реальные данные + BaseBadge | Modify |

---

## Task 1: Миграция 005 — users.client_id

**Files:**
- Create: `backend/migrations/005_users_client_id.sql`
- Modify: `backend/migrations/runner.py`
- Modify: `backend/startup/db_init.py`

- [ ] **Step 1: Создать SQL-миграцию**

`backend/migrations/005_users_client_id.sql`:
```sql
-- Migration 005: add client_id to users (links auth user → clients company).
-- Foundation for Group C domains (defects, orders, machinery bound to client company).
-- Idempotent: guarded by information_schema check.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'users'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'client_id'
        ) THEN
            ALTER TABLE users ADD COLUMN client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL;
        END IF;
    END IF;
END $$;
```

- [ ] **Step 2: Добавить `apply_migration_005` в runner + вызов в `apply_all`**

В `backend/migrations/runner.py`, после `apply_migration_004`:
```python
def apply_migration_005(conn) -> None:
    """Apply migration 005 — add client_id to users (auth user → clients company link)."""
    sql_path = _MIGRATIONS_DIR / "005_users_client_id.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 005_users_client_id.sql applied.")
```
В `apply_all` добавить `apply_migration_005(conn)` после `apply_migration_004(conn)`.

- [ ] **Step 3: Добавить `client_id` в `db_init.py` (оба блока users)**

В `init_catalog_tables()` найти блок `CREATE TABLE IF NOT EXISTS users` для PG (~строка 71-81) — добавить `client_id INTEGER` (без FK в SQLite-блоке; FK только через миграцию 005 для PG). Также добавить в `migrate_users_columns()` (если есть) или создать новую миграцию-функцию.

- [ ] **Step 4: Коммит**

```bash
git add backend/migrations/005_users_client_id.sql backend/migrations/runner.py backend/startup/db_init.py
git commit -m "feat(migration): 005 add users.client_id (auth user → clients link)"
```

---

## Task 2: auth_deps — вернуть client_id

**Files:**
- Modify: `backend/auth_deps.py`

- [ ] **Step 1: Прочитать auth_deps.py, найти get_current_user**

Найти где формируется dict `{"id", "username", "name", "role"}` — добавить `client_id`.

- [ ] **Step 2: Добавить client_id в возвращаемый dict**

В `get_current_user` (и async-версия, если есть), после получения user из БД/токена, добавить `client_id` в возвращаемый dict. Если колонки нет в старой БД — вернуть `None` (безопасно).

Прочитать точный код и добавить:
```python
# в формировании user dict:
"client_id": user_row.get("client_id") if hasattr(user_row, 'get') else user_row[...] # адаптировать под реальный код
```

- [ ] **Step 3: Коммит**

```bash
git add backend/auth_deps.py
git commit -m "feat(auth): return client_id in get_current_user (for Group C domains)"
```

---

## Task 3: Миграция 006 — таблица defects

**Files:**
- Create: `backend/migrations/006_defects.sql`
- Modify: `backend/migrations/runner.py`
- Modify: `backend/startup/db_init.py`

- [ ] **Step 1: Создать SQL-миграцию**

`backend/migrations/006_defects.sql`:
```sql
-- Migration 006: defects table (дефектовка оборудования клиентов).
-- Idempotent (CREATE TABLE IF NOT EXISTS).
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
```

- [ ] **Step 2: apply_migration_006 в runner + apply_all**

Аналогично Task 1 Step 2.

- [ ] **Step 3: defects table в db_init.py (оба блока)**

В `init_catalog_tables()` добавить `CREATE TABLE IF NOT EXISTS defects (...)` для PG (с FK) и SQLite (без FK). Поля те же.

- [ ] **Step 4: Коммит**

```bash
git add backend/migrations/006_defects.sql backend/migrations/runner.py backend/startup/db_init.py
git commit -m "feat(migration): 006 defects table (дефектовка)"
```

---

## Task 4: Backend — schemas + service

**Files:**
- Create: `backend/schemas/defects.py`
- Create: `backend/services/defects_service.py`

- [ ] **Step 1: Создать Pydantic-схемы**

`backend/schemas/defects.py`:
```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class DefectCreate(BaseModel):
    equipment: str
    bearing: Optional[str] = None
    description: str = ""
    status: str = "new"
    action: Optional[str] = None
    detected_at: Optional[str] = None
    client_id: Optional[int] = None  # only for admin/manager; client ignores, uses own


class DefectUpdate(BaseModel):
    equipment: Optional[str] = None
    bearing: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    action: Optional[str] = None
    detected_at: Optional[str] = None
```

- [ ] **Step 2: Создать defects_service.py (по эталону notes_service)**

`backend/services/defects_service.py`:
```python
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import get_db, q, _use_pg


def _resolve_client_id(current_user: Dict[str, Any], explicit: Optional[int]) -> int:
    """Client role: always own client_id. Admin/manager: explicit or None (filter)."""
    role = current_user.get("role")
    own = current_user.get("client_id")
    if role == "client":
        if not own:
            raise HTTPException(403, "Ваш аккаунт не привязан к клиенту. Обратитесь к администратору.")
        return own
    return explicit if explicit is not None else 0  # 0 = all (admin)


async def list_defects(
    current_user: Dict[str, Any],
    client_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()

    role = current_user.get("role")
    own = current_user.get("client_id")

    if role == "client" and own:
        cursor.execute(
            q("""SELECT id, client_id, created_by, equipment, bearing, description, status, action,
                detected_at, created_at, updated_at
                FROM defects WHERE client_id = %s ORDER BY created_at DESC"""),
            (own,),
        )
    elif client_id:
        cursor.execute(
            q("""SELECT id, client_id, created_by, equipment, bearing, description, status, action,
                detected_at, created_at, updated_at
                FROM defects WHERE client_id = %s ORDER BY created_at DESC"""),
            (client_id,),
        )
    else:
        cursor.execute(
            q("""SELECT id, client_id, created_by, equipment, bearing, description, status, action,
                detected_at, created_at, updated_at
                FROM defects ORDER BY created_at DESC"""),
        )

    rows = cursor.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


async def create_defect(
    data: Any,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    role = current_user.get("role")
    own = current_user.get("client_id")
    if role == "client":
        if not own:
            conn.close()
            raise HTTPException(403, "Ваш аккаунт не привязан к клиенту.")
        target_client_id = own
    else:
        target_client_id = data.client_id or own or 0

    now = datetime.now().isoformat()
    cursor.execute(
        q("""INSERT INTO defects (client_id, created_by, equipment, bearing, description, status, action, detected_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""),
        (
            target_client_id,
            current_user["id"],
            data.equipment,
            data.bearing,
            data.description,
            data.status,
            data.action,
            data.detected_at,
            now,
            now,
        ),
    )
    if _use_pg:
        cursor.execute("SELECT LASTVAL()")
    else:
        cursor.execute("SELECT last_insert_rowid()")
    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    return {
        "id": new_id,
        "client_id": target_client_id,
        "created_by": current_user["id"],
        "equipment": data.equipment,
        "bearing": data.bearing,
        "description": data.description,
        "status": data.status,
        "action": data.action,
        "detected_at": data.detected_at,
        "created_at": now,
        "updated_at": now,
    }


async def update_defect(
    defect_id: int,
    data: Any,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT id, client_id FROM defects WHERE id = %s"), (defect_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Дефект не найден")

    defect_client_id = row[1]
    _check_access(current_user, defect_client_id)

    now = datetime.now().isoformat()
    fields = []
    values = []
    for fname in ("equipment", "bearing", "description", "status", "action", "detected_at"):
        val = getattr(data, fname)
        if val is not None:
            fields.append(f"{fname} = %s")
            values.append(val)
    if not fields:
        conn.close()
        raise HTTPException(400, "Нет полей для обновления")
    fields.append("updated_at = %s")
    values.append(now)
    values.append(defect_id)

    cursor.execute(q(f"UPDATE defects SET {', '.join(fields)} WHERE id = %s"), values)
    conn.commit()
    conn.close()

    return {"id": defect_id, "updated_at": now, "ok": True}


async def delete_defect(
    defect_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT client_id FROM defects WHERE id = %s"), (defect_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Дефект не найден")

    _check_access(current_user, row[0])

    cursor.execute(q("DELETE FROM defects WHERE id = %s"), (defect_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


def _check_access(current_user: Dict[str, Any], defect_client_id: Any) -> None:
    role = current_user.get("role")
    own = current_user.get("client_id")
    if role == "client" and own != defect_client_id:
        raise HTTPException(403, "Forbidden")
    # admin/manager: no restriction


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "client_id": r[1],
        "created_by": r[2],
        "equipment": r[3],
        "bearing": r[4],
        "description": r[5],
        "status": r[6],
        "action": r[7],
        "detected_at": r[8],
        "created_at": r[9] or "",
        "updated_at": r[10] or "",
    }
```

- [ ] **Step 3: Коммит**

```bash
git add backend/schemas/defects.py backend/services/defects_service.py
git commit -m "feat(defects): schemas + service (CRUD + owner-check)"
```

---

## Task 5: Backend — router + регистрация + тесты

**Files:**
- Create: `backend/routes/defects.py`
- Modify: `backend/routes/index.py`
- Create: `backend/tests/test_defects_crud.py`

- [ ] **Step 1: Создать router (по эталону notes.py)**

`backend/routes/defects.py`:
```python
from __future__ import annotations
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from schemas.defects import DefectCreate, DefectUpdate

from auth_deps import get_current_user as _get_current_user
from services.defects_service import (
    create_defect,
    delete_defect,
    list_defects,
    update_defect,
)

router = APIRouter(tags=["defects"])


def get_current_user():
    async def _dep(request):
        return _get_current_user(request)
    return _dep


@router.get("/api/defects")
async def list_defects_endpoint(
    client_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_defects(current_user=current_user, client_id=client_id)


@router.post("/api/defects")
async def create_defect_endpoint(
    data: DefectCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_defect(data=data, current_user=current_user)


@router.patch("/api/defects/{defect_id}")
async def update_defect_endpoint(
    defect_id: int,
    data: DefectUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await update_defect(defect_id=defect_id, data=data, current_user=current_user)


@router.delete("/api/defects/{defect_id}")
async def delete_defect_endpoint(
    defect_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_defect(defect_id=defect_id, current_user=current_user)
```

- [ ] **Step 2: Зарегистрировать роутер в index.py**

В `backend/routes/index.py`, функция `register_routes(app)`:
```python
from routes.defects import router as defects_router
app.include_router(defects_router)
```

- [ ] **Step 3: Написать тесты**

`backend/tests/test_defects_crud.py` (TDD, sync через asyncio.run как в test_notes):
```python
"""Tests for defects CRUD + owner-check + client_id binding."""
import asyncio
import os

import psycopg2
import pytest

from services.defects_service import list_defects, create_defect, update_defect, delete_defect
from schemas.defects import DefectCreate, DefectUpdate


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_defects(db_conn, monkeypatch):
    import services.defects_service as svc

    cur = db_conn.cursor()
    # ensure tables exist (clients + users + defects)
    cur.execute("DROP TABLE IF EXISTS defects CASCADE")
    cur.execute("DROP TABLE IF EXISTS clients CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("""CREATE TABLE clients (id SERIAL PRIMARY KEY, name TEXT)""")
    cur.execute("""CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT, client_id INTEGER)""")
    cur.execute("""
        CREATE TABLE defects (
            id SERIAL PRIMARY KEY,
            client_id INTEGER,
            created_by INTEGER,
            equipment TEXT NOT NULL,
            bearing TEXT,
            description TEXT,
            status TEXT DEFAULT 'new',
            action TEXT,
            detected_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    cur.execute("INSERT INTO clients (name) VALUES ('ООО Ромашка'), ('ООО Вектор')")
    cur.execute("INSERT INTO users (username, role, client_id) VALUES ('client1','client',1), ('admin','admin',NULL)")
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    def _test_get_db():
        return psycopg2.connect(TEST_DSN)
    monkeypatch.setattr(svc, "get_db", _test_get_db)


def test_create_defect_as_client_binds_own_client_id(seeded_defects):
    client_user = {"id": 1, "role": "client", "client_id": 1}
    d = _run(create_defect(data=DefectCreate(equipment="Нория №1", description="Шум"), current_user=client_user))
    assert d["client_id"] == 1
    assert d["created_by"] == 1


def test_list_defects_client_sees_only_own(seeded_defects):
    _run(create_defect(data=DefectCreate(equipment="A"), current_user={"id": 1, "role": "client", "client_id": 1}))
    _run(create_defect(data=DefectCreate(equipment="B"), current_user={"id": 99, "role": "admin"}))  # client_id=0
    mine = _run(list_defects(current_user={"id": 1, "role": "client", "client_id": 1}))
    assert len(mine) == 1
    assert mine[0]["equipment"] == "A"


def test_list_defects_admin_sees_all(seeded_defects):
    _run(create_defect(data=DefectCreate(equipment="A"), current_user={"id": 1, "role": "client", "client_id": 1}))
    _run(create_defect(data=DefectCreate(equipment="B", client_id=2), current_user={"id": 2, "role": "admin"}))
    all_d = _run(list_defects(current_user={"id": 2, "role": "admin"}))
    assert len(all_d) >= 2


def test_update_defect_owner_check(seeded_defects):
    d = _run(create_defect(data=DefectCreate(equipment="X"), current_user={"id": 1, "role": "client", "client_id": 1}))
    # another client tries to update
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run(update_defect(defect_id=d["id"], data=DefectUpdate(status="resolved"),
                           current_user={"id": 99, "role": "client", "client_id": 2}))
    assert exc.value.status_code == 403


def test_delete_defect_owner_check(seeded_defects):
    d = _run(create_defect(data=DefectCreate(equipment="X"), current_user={"id": 1, "role": "client", "client_id": 1}))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run(delete_defect(defect_id=d["id"], current_user={"id": 99, "role": "client", "client_id": 2}))
    assert exc.value.status_code == 403
```

- [ ] **Step 4: Прогнать тесты**

Run: `cd backend && python -m pytest tests/test_defects_crud.py -v`
Expected: 5 passed.

- [ ] **Step 5: Полный набор**

Run: `cd backend && python -m pytest -q`
Expected: 97 + 5 = 102.

- [ ] **Step 6: Коммит**

```bash
git add backend/routes/defects.py backend/routes/index.py backend/tests/test_defects_crud.py
git commit -m "feat(defects): router /api/defects + registration + CRUD tests"
```

---

## Task 6: Frontend — types + api + store

**Files:**
- Create: `src/types/defect.ts`
- Create: `src/api/defects.ts`
- Create: `src/stores/defects.ts`

- [ ] **Step 1: Типы**

`src/types/defect.ts`:
```ts
export type DefectStatus = 'new' | 'critical' | 'replacement_ordered' | 'resolved'

export interface Defect {
  id: number
  client_id: number
  created_by?: number
  equipment: string
  bearing?: string
  description: string
  status: DefectStatus
  action?: string
  detected_at?: string
  created_at: string
  updated_at: string
}
```

- [ ] **Step 2: API (по эталону notes.ts)**

`src/api/defects.ts`:
```ts
import { api } from './client'
import type { Defect } from '@/types/defect'

export const defectsApi = {
  list: (params?: { client_id?: number }) => api.get<Defect[]>('/api/defects', { params }),
  create: (data: Partial<Defect>) => api.post<Defect>('/api/defects', data),
  update: (id: number, data: Partial<Defect>) => api.patch<Defect>(`/api/defects/${id}`, data),
  remove: (id: number) => api.delete(`/api/defects/${id}`),
}
```

- [ ] **Step 3: Store (по эталону notes store)**

`src/stores/defects.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Defect } from '@/types/defect'
import { defectsApi } from '@/api/defects'

export const useDefectsStore = defineStore('defects', () => {
  const items = ref<Defect[]>([])
  const loading = ref(false)

  async function load(params?: { client_id?: number }) {
    loading.value = true
    try {
      const { data } = await defectsApi.list(params)
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<Defect>) {
    const { data: created } = await defectsApi.create(data)
    items.value.unshift(created)
    return created
  }

  async function update(id: number, patch: Partial<Defect>) {
    const { data } = await defectsApi.update(id, patch)
    const local = items.value.find((x) => x.id === id)
    if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    await defectsApi.remove(id)
    items.value = items.value.filter((x) => x.id !== id)
  }

  return { items, loading, load, create, update, remove }
})
```

- [ ] **Step 4: Smoke build**

Run: `npm run build`
Expected: success.

- [ ] **Step 5: Коммит**

```bash
git add src/types/defect.ts src/api/defects.ts src/stores/defects.ts
git commit -m "feat(defects-fe): types + api + store"
```

---

## Task 7: DefectsView — реальные данные + BaseBadge

**Files:**
- Modify: `src/views/client/DefectsView.vue`

- [ ] **Step 1: Прочитать текущий DefectsView.vue**

Понять структуру: мок-массив, addDefect local-only, таблица с бейджами.

- [ ] **Step 2: Переписать на store + реальные данные**

Полный новый `<script setup>`:
```ts
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useDefectsStore } from '@/stores/defects'
import { toast } from '@/plugins/toast'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import type { DefectStatus } from '@/types/defect'

const store = useDefectsStore()

const newDefect = ref({ equipment: '', bearing: '', description: '' })
const loading = ref(false)

const STATUS_MAP: Record<DefectStatus, { label: string; type: 'success'|'warning'|'danger'|'info'|'gray' }> = {
  new: { label: 'Новый', type: 'gray' },
  critical: { label: 'Критично', type: 'danger' },
  replacement_ordered: { label: 'Заказана замена', type: 'warning' },
  resolved: { label: 'Решено', type: 'success' },
}

async function addDefect() {
  if (!newDefect.value.equipment.trim()) {
    toast.warning('Укажите оборудование')
    return
  }
  loading.value = true
  try {
    await store.create({
      equipment: newDefect.value.equipment,
      bearing: newDefect.value.bearing || undefined,
      description: newDefect.value.description,
      status: 'new',
    })
    newDefect.value = { equipment: '', bearing: '', description: '' }
    toast.success('Дефект добавлен')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || 'Ошибка сохранения')
  } finally {
    loading.value = false
  }
}

async function removeDefect(id: number) {
  try {
    await store.remove(id)
    toast.success('Дефект удалён')
  } catch (e: any) {
    toast.error('Ошибка удаления')
  }
}

onMounted(() => store.load().catch(() => toast.error('Не удалось загрузить дефекты')))
</script>
```

Template: таблица `v-for="d in store.items"` с колонками equipment/bearing/description/status(BaseBadge)/detected_at + кнопка удаления. Форма добавления (3 input + button). Empty-state «Дефектов пока нет».

(Точный template — адаптировать под текущую структуру, заменив `defects` ref → `store.items`, бейджи → `<BaseBadge :type="STATUS_MAP[d.status].type">{{ STATUS_MAP[d.status].label }}</BaseBadge>`.)

- [ ] **Step 3: Smoke build**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Коммит**

```bash
git add src/views/client/DefectsView.vue
git commit -m "feat(defects-view): real API data + BaseBadge statuses + toast"
```

---

## Task 8: Деплой + проверка + merge

**Files:** — (операционный)

- [ ] **Step 1: Полный набор тестов + build**

```bash
cd backend && python -m pytest -q   # 102 passed
cd .. && npm run build              # success
```

- [ ] **Step 2: Деплой backend (миграции применятся при старте) + frontend**

```bash
ssh root@72.56.246.21 "cd /var/www/crmks && git pull origin main && systemctl restart crmks-api && sleep 5"
# verify migrations applied:
ssh root@72.56.246.21 "psql ... -c '\d defects' | head -15"
# frontend:
scp -r dist/* root@72.56.246.21:/var/www/crmks/dist/
ssh root@72.56.246.21 "nginx -s reload"
```

- [ ] **Step 3: Live-проверка /api/defects на https://crmdot.ru**

```bash
# login → token → POST defect → GET list
```

- [ ] **Step 4: Merge в main**

```bash
git checkout main && git merge feat/defects-domain --no-ff -m "Merge defects domain + users.client_id migration"
git push origin main
```

---

## Self-Review

**1. Spec coverage:**
- users.client_id миграция → Task 1. ✓
- auth_deps возвращает client_id → Task 2. ✓
- defects таблица + миграция → Task 3. ✓
- schemas + service (CRUD + owner-check) → Task 4. ✓
- router + тесты → Task 5. ✓
- frontend types/api/store → Task 6. ✓
- DefectsView реальные данные + BaseBadge → Task 7. ✓
- деплой → Task 8. ✓

**2. Placeholder scan:** код в шагах финальный; DefectsView template дан как описание (адаптировать под текущую структуру — исполнитель читает файл).

**3. Type consistency:**
- `DefectStatus` = 'new'|'critical'|'replacement_ordered'|'resolved' — едино в types, store, STATUS_MAP.
- `DefectCreate.client_id` — только для admin; client игнорирует (берёт свой) — описано в service `_resolve_client_id`.
- `get_current_user` возвращает `client_id` — Task 2; используется в service Task 4.
