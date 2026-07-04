# Defects домен + users.client_id миграция — Design

> **Цель:** Построить настоящий backend для дефектовки (CRUD) + предварительную миграцию `users.client_id` (фундамент для всех доменов Группы C). Заменить захардкоженный `client/DefectsView.vue` на реальные API-данные.

## Решения (из brainstorming с заказчиком)

| Вопрос | Решение |
|---|---|
| Связь user↔client | **Вариант B**: добавить `client_id` в таблицу `users` + обновить `get_current_user`. Defects привязаны к `client_id` (компании). |
| Статус дефекта | **Enum**: `new`, `critical`, `replacement_ordered`, `resolved`. Фронт мапит на русские лейблы + BaseBadge (danger/warning/info/success). |
| Кто создаёт дефекты | **Client + admin/manager**. Client создаёт свои (привязка к своему client_id), admin/manager — от имени любого клиента + видят все. |
| Backend-паттерн | Следовать эталону `notes`: router → service → db, `Depends(get_current_user())`, dual-dialect PG+SQLite через `q()`. |
| Где создавать таблицу | `init_catalog_tables()` в `db_init.py` (оба блока PG+SQLite) + миграция `005` для чистого PG (idempotent). |

---

## Архитектура

### Предварительная задача: миграция `users.client_id`

```
users table:
  + client_id INTEGER NULL REFERENCES clients(id) ON DELETE SET NULL
```

Это связывает auth-пользователя (роль `client`) с записью в `clients`. Обновление:
- `backend/auth_deps.py` — `get_current_user` возвращает `client_id` в dict (если есть).
- `backend/startup/db_init.py` — добавить колонку в обоих блоках + `migrate_users_columns()`.
- Миграция `005` (PG, idempotent) для существующих БД.

После этого `current_user["client_id"]` доступен во всех эндпоинтах.

### Домен Defects

```
defects table:
  id              SERIAL PK
  client_id       INTEGER REFERENCES clients(id) ON DELETE CASCADE   -- компания-владелец
  created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL    -- кто завёл (audit)
  equipment       VARCHAR(300) NOT NULL     -- "Виброгрохот ГИЛ-42"
  bearing         VARCHAR(300)              -- "HHB 22315-E1-T41A" (nullable)
  description     TEXT                      -- описание дефекта
  status          VARCHAR(50) DEFAULT 'new' -- enum: new|critical|replacement_ordered|resolved
  action          TEXT                      -- "Заказана замена" (nullable)
  detected_at     VARCHAR(100)              -- ISO-строка даты обнаружения
  created_at      VARCHAR(100)
  updated_at      VARCHAR(100)
```

**CRUD эндпоинты (`/api/defects`):**
- `GET /api/defects` — список. Client видит `WHERE client_id = current_user.client_id`. Admin/manager видят все (опционально с фильтром `?client_id=`).
- `POST /api/defects` — создать. Client: `client_id = current_user.client_id` (авто). Admin/manager: `client_id` из тела запроса.
- `PATCH /api/defects/{id}` — обновить. Owner-check: client может только свои, admin — любые.
- `DELETE /api/defects/{id}` — удалить. Owner-check как выше.

**Pydantic-схема (`backend/schemas/defects.py`):**
```python
class DefectCreate(BaseModel):
    equipment: str
    bearing: Optional[str] = None
    description: str
    status: str = "new"           # new|critical|replacement_ordered|resolved
    action: Optional[str] = None
    detected_at: Optional[str] = None
    client_id: Optional[int] = None   # только для admin/manager (client игнорируется, берётся свой)

class DefectUpdate(BaseModel):
    equipment: Optional[str] = None
    bearing: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    action: Optional[str] = None
    detected_at: Optional[str] = None
```

---

## File Structure

| Файл | Ответственность | Статус |
|---|---|---|
| `backend/migrations/005_users_client_id.sql` | ALTER TABLE users ADD client_id (PG, idempotent) | Create |
| `backend/migrations/runner.py` | `apply_migration_005` + вызов в `apply_all` | Modify |
| `backend/startup/db_init.py` | `client_id` в обоих блоках users + `migrate_users_columns` | Modify |
| `backend/auth_deps.py` | `get_current_user` возвращает `client_id` | Modify |
| `backend/migrations/006_defects.sql` | CREATE TABLE defects (PG, idempotent, FK + индексы) | Create |
| `backend/startup/db_init.py` | defects table в обоих блоках | Modify |
| `backend/schemas/defects.py` | `DefectCreate`, `DefectUpdate` | Create |
| `backend/services/defects_service.py` | CRUD: list/create/update/delete + owner-check | Create |
| `backend/routes/defects.py` | эндпоинты `/api/defects` + регистрация в index.py | Create |
| `backend/routes/index.py` | `app.include_router(defects_router)` | Modify |
| `backend/tests/test_defects.py` | Тесты CRUD + owner-check + client_id binding | Create |
| `src/types/defect.ts` | TS-тип `Defect` | Create |
| `src/api/defects.ts` | `defectsApi` (list/create/update/remove) | Create |
| `src/stores/defects.ts` | Pinia store (items, list, create, update, remove) | Create |
| `src/views/client/DefectsView.vue` | Реальные API-данные вместо моков + BaseBadge для статусов | Modify |

---

## Детали реализации

### Backend (по эталону notes)

**`backend/services/defects_service.py`** — функции `list_defects`, `create_defect`, `update_defect`, `delete_defect`. Каждая принимает `current_user`. Owner-check: `client_id = current_user.get("client_id")` для client-роли; admin/manager видят/меняют все. `created_by = current_user["id"]` при создании.

**`backend/routes/defects.py`** — thin-слой:
```python
@router.get("/api/defects")
async def list_defects_endpoint(client_id: Optional[int] = None, current_user = Depends(get_current_user())):
    return await list_defects(current_user=current_user, client_id=client_id)

@router.post("/api/defects")
async def create_defect_endpoint(data: DefectCreate, current_user = Depends(get_current_user())):
    return await create_defect(data=data, current_user=current_user)
# ... PATCH, DELETE
```

### Frontend

**`src/types/defect.ts`:**
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

**`src/api/defects.ts`** + **`src/stores/defects.ts`** — по эталону notes (list/create/update/remove).

**`src/views/client/DefectsView.vue`** — переписать на store: `onMounted(() => store.load())`, удалить захардкоженный массив + `addDefect` local-only. Статусы → BaseBadge с маппингом:
- `new` → gray «Новый»
- `critical` → danger «Критично»
- `replacement_ordered` → warning «Заказана замена»
- `resolved` → success «Решено»

Форма создания: equipment (input), bearing (input), description (textarea), status (select). Toast на успех/ошибку (из волны 1).

---

## Тестирование

Backend (pytest, по эталону test_notes_tag_filter):
- `test_create_defect_as_client_binds_client_id` — client создаёт, defects.client_id = его client_id
- `test_list_defects_client_sees_only_own` — client видит только свои
- `test_list_defects_admin_sees_all` — admin видит все
- `test_update_defect_owner_check` — client не может менять чужие (403)
- `test_delete_defect_owner_check` — client не может удалить чужие (403)

Frontend: smoke через `npm run build` + ручная проверка в браузере.

---

## Что НЕ в этой задаче

- Machinery/Orders/Reports — следующие домены Группы C (каждый свой цикл).
- Admin-версия DefectsView с расширенными фильтрами — можно позже (сейчас admin видит через тот же экран, фильтр по client_id опционален).
- Массовый импорт дефектов — YAGNI.
- Привязка дефектов к machinery_id — пока equipment/bearing как строки (machinery таблицы ещё нет; добавим FK когда Machinery будет построен).
