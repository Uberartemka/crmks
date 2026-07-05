# Аватарки пользователей + минимальный ЛК — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить аватарки пользователей (загружаемые через файлов сервис) с fallback на инициалы+цвет, отображение в чате/sidebar/персонал/ЛК, и минимальную страницу `/profile` для смены своего аватара.

**Architecture:** Миграция 011 (`users.avatar_file_id` → files). Backend: `UserOut.avatar_url` (вычисляется из `avatar_file_id`), `PATCH /api/users/me/avatar` (validates `uploaded_by`), расширение `me`/`list_users`/chat members. Frontend: `Avatar.vue` (img или инициалы+HSL hue из name), `ProfileView.vue` (мин ЛК), `FileUploader` drag-drop, интеграция в 4 места.

**Tech Stack:** FastAPI + psycopg2 + pytest (backend), Vue 3 + TypeScript + Pinia + vue-router + vitest + vue-toastification (frontend).

**Spec:** `docs/superpowers/specs/2026-07-05-user-avatars-profile-design.md`

---

## File Structure

**Backend:**
- `backend/migrations/011_user_avatars.sql` (create) + `backend/migrations/runner.py` (register)
- `backend/schemas/auth.py` (modify) — `UserOut.avatar_file_id` + `avatar_url`
- `backend/routes/index.py` (modify) — `me`, `list_users`, новый `PATCH /api/users/me/avatar`
- `backend/services/chat_service.py` (modify) — chat members получают `avatar_file_id`/`avatar_url`
- `backend/tests/test_avatars.py` (create) — 5 backend тестов

**Frontend:**
- `src/components/ui/Avatar.vue` (create) + `Avatar.test.ts` (create)
- `src/components/ui/FileUploader.vue` (modify) — drag-drop zone
- `src/views/ProfileView.vue` (create)
- `src/stores/auth.ts` (modify) — `avatarUrl` getter + `updateAvatar`
- `src/composables/useChatAdapter.ts` (modify) — `users[].avatar`
- `src/types/chat.ts` (modify) — `Channel.members[].avatar_url`
- `src/types/auth.ts` (modify) — `User.avatar_file_id` + `avatar_url`
- `src/components/sidebar/AppSidebar.vue` (modify) — аватар + ссылка Профиль
- `src/views/admin/PersonnelView.vue` (modify) — колонка аватара
- `src/router/index.ts` (modify) — `/profile` route

---

## Task 1: Миграция 011 + регистрация

**Files:**
- Create: `backend/migrations/011_user_avatars.sql`
- Modify: `backend/migrations/runner.py`

- [ ] **Step 1: Создать `backend/migrations/011_user_avatars.sql`**

```sql
-- Migration 011: user avatars. Idempotent (information_schema guard).
-- Assumes users + files tables exist (files from migration 010).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
          AND column_name = 'avatar_file_id'
    ) THEN
        ALTER TABLE users
            ADD COLUMN avatar_file_id BIGINT NULL REFERENCES files(id) ON DELETE SET NULL;
    END IF;
END $$;
```

- [ ] **Step 2: Добавить `apply_migration_011` в `runner.py`**

После `apply_migration_010` (перед `apply_all`) добавить функцию по образцу 010:

```python
def apply_migration_011(conn) -> None:
    """Apply migration 011 — user avatars (users.avatar_file_id → files)."""
    sql_path = _MIGRATIONS_DIR / "011_user_avatars.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 011_user_avatars.sql applied.")
```

В `apply_all`, после `apply_migration_010(conn)`, добавить:
```python
        apply_migration_011(conn)
```

- [ ] **Step 3: Verify migration applies**

Run: `cd backend && python -c "from migrations.runner import apply_migration_011; from db import PG_URL; import psycopg2; c=psycopg2.connect(PG_URL); apply_migration_011(c); c.close(); print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/011_user_avatars.sql backend/migrations/runner.py
git commit -m "feat(avatars-db): migration 011 — users.avatar_file_id"
```

---

## Task 2: `UserOut` schema + `me`/`list_users` отдают avatar_url

**Files:**
- Modify: `backend/schemas/auth.py`
- Modify: `backend/routes/index.py` (`me` функция ~строка 87, `list_users` ~92)
- Test: `backend/tests/test_avatars.py` (create)

- [ ] **Step 1: Расширить `UserOut` в `backend/schemas/auth.py`**

Текущая `UserOut` (прочитать, затем добавить 2 поля):

```python
class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    avatar_file_id: Optional[int] = None
    avatar_url: Optional[str] = None
```

- [ ] **Step 2: Создать `backend/tests/test_avatars.py` с фикстурой + 2 теста**

```python
"""Tests for user avatars: avatar_url in me/list_users, PATCH endpoint."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from routes.index import _avatar_url  # helper (создаётся в Task 3, пока заглушка — увидите ниже)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_avatars(db_conn, monkeypatch):
    """Seed users + files; patch get_db."""
    import routes.index as idx
    import services.chat_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS messages CASCADE")
    cur.execute("DROP TABLE IF EXISTS channels CASCADE")
    cur.execute("DROP TABLE IF EXISTS files CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute(
        "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, password_hash TEXT, "
        "name TEXT, role TEXT, client_id INTEGER, avatar_file_id BIGINT NULL, created_at TEXT)"
    )
    cur.execute(
        "CREATE TABLE files (id BIGSERIAL PRIMARY KEY, uploaded_by INTEGER, storage_path TEXT, "
        "thumbnail_path TEXT, original_name TEXT, mime_type TEXT, size_bytes BIGINT, "
        "sha256 TEXT, is_image BOOLEAN DEFAULT false, created_at TIMESTAMPTZ DEFAULT now())"
    )
    cur.execute(
        "INSERT INTO users (username, password_hash, name, role) VALUES "
        "('alice', 'x', 'Алиса', 'manager'), ('bob', 'x', 'Боб', 'manager')"
    )
    cur.execute(
        "INSERT INTO files (uploaded_by, storage_path, original_name, mime_type, size_bytes, sha256, is_image) "
        "VALUES (1, '2026/07/a.png', 'ava.png', 'image/png', 100, 'abc', true)"
    )
    cur.execute("UPDATE users SET avatar_file_id = 1 WHERE id = 1")
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(idx, "get_db", _test_get_db)
    monkeypatch.setattr(svc, "get_db", _test_get_db)


def test_avatar_url_helper():
    assert _avatar_url(1) == "/api/files/1"
    assert _avatar_url(None) is None


def test_me_returns_avatar_url_when_set(seeded_avatars):
    from routes.index import me
    out = me(current_user={"id": 1, "username": "alice", "name": "Алиса", "role": "manager", "client_id": None})
    # me возвращает dict (прочитайте сигнатуру в routes/index.py и при необходимости адаптируйте)
    assert out["avatar_file_id"] == 1
    assert out["avatar_url"] == "/api/files/1"


def test_me_avatar_url_null_when_no_avatar(seeded_avatars):
    from routes.index import me
    out = me(current_user={"id": 2, "username": "bob", "name": "Боб", "role": "manager", "client_id": None})
    assert out["avatar_file_id"] is None
    assert out["avatar_url"] is None
```

> **Примечание для исполнителя:** Прочитайте текущую функцию `me` в `routes/index.py` (~строка 87). Она делает `SELECT id, password_hash, name, role, client_id FROM users WHERE id = %s` для login, но `me` (GET /api/auth/me) использует `current_user` напрямую без нового SELECT. Скорее всего, `avatar_file_id` нужно добавить в SELECT в `auth_deps.get_current_user` (чтобы current_user уже содержал его). Прочитайте `auth_deps.py` и решите: либо расширить SELECT в `get_current_user`, либо делать отдельный SELECT в `me`. В плане ниже (Task 3) — расширяем `get_current_user`. Адаптируйте тест соответственно.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_avatars.py -v`
Expected: FAIL — `_avatar_url` ещё не существует, `me` не возвращает avatar поля.

- [ ] **Step 4: Добавить `_avatar_url` helper + расширить SELECT'ы**

В `backend/routes/index.py` вверху (после импортов) добавить:
```python
def _avatar_url(avatar_file_id: int | None) -> str | None:
    """Build the download URL for a user's avatar, or None if not set."""
    return f"/api/files/{avatar_file_id}" if avatar_file_id else None
```

В `backend/auth_deps.py` функция `get_current_user` — текущий SELECT:
```python
q("SELECT id, username, name, role, client_id FROM users WHERE id = %s")
```
Заменить на:
```python
q("SELECT id, username, name, role, client_id, avatar_file_id FROM users WHERE id = %s")
```
И в returned dict добавить:
```python
"avatar_file_id": row[5],
```

(То же самое — в `get_current_user_async`, тот же SELECT + row[5].)

В `routes/index.py` функция `me` — текущий `return current_user` уже возвращает расширенный dict (т.к. `get_current_user` теперь его наполняет). Добавить вычисление `avatar_url`:
```python
@router.get("/api/auth/me")
def me(current_user: dict = Depends(get_current_user_dep)):
    return {
        **current_user,
        "avatar_url": _avatar_url(current_user.get("avatar_file_id")),
    }
```

В `list_users` — текущий SELECT `SELECT u.id, u.username, u.name, u.role, u.client_id, c.name FROM users u LEFT JOIN clients c ...`. Добавить `u.avatar_file_id`:
```python
"""SELECT u.id, u.username, u.name, u.role, u.client_id, c.name, u.avatar_file_id
    FROM users u LEFT JOIN clients c ON c.id = u.client_id
    ORDER BY u.name"""
```
В list-comprehension ответа добавить:
```python
"avatar_file_id": r[6],
"avatar_url": _avatar_url(r[6]),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_avatars.py -v`
Expected: PASS (3 теста: helper + me_with_avatar + me_without_avatar).

- [ ] **Step 6: Run full backend suite (regression)**

Run: `cd backend && python -m pytest -q`
Expected: PASS (раньше 174; +3 новых = 177).

- [ ] **Step 7: Commit**

```bash
git add backend/schemas/auth.py backend/routes/index.py backend/auth_deps.py backend/tests/test_avatars.py
git commit -m "feat(avatars-api): UserOut.avatar_url + me/list_users return avatar fields"
```

---

## Task 3: `PATCH /api/users/me/avatar` endpoint

**Files:**
- Modify: `backend/routes/index.py` — новый endpoint + `AvatarUpdate` schema
- Test: `backend/tests/test_avatars.py` — 2 теста

- [ ] **Step 1: Добавить 2 теста в `backend/tests/test_avatars.py`**

```python
def test_update_my_avatar_sets_file_id(seeded_avatars):
    from routes.index import update_my_avatar, AvatarUpdate
    out = update_my_avatar(
        data=AvatarUpdate(file_id=1),
        current_user={"id": 1, "username": "alice", "name": "Алиса", "role": "manager", "client_id": None, "avatar_file_id": None},
    )
    assert out["ok"] is True
    assert out["avatar_file_id"] == 1
    assert out["avatar_url"] == "/api/files/1"
    # DB updated
    conn = psycopg2.connect(os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"))
    cur = conn.cursor()
    cur.execute("SELECT avatar_file_id FROM users WHERE id = 1")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_update_my_avatar_other_users_file_403(seeded_avatars):
    from routes.index import update_my_avatar, AvatarUpdate
    # file 1 was uploaded_by=1 (alice); bob (id=2) tries to use it
    with pytest.raises(HTTPException) as exc:
        update_my_avatar(
            data=AvatarUpdate(file_id=1),
            current_user={"id": 2, "username": "bob", "name": "Боб", "role": "manager", "client_id": None, "avatar_file_id": None},
        )
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_avatars.py -k "update_my_avatar" -v`
Expected: FAIL — `update_my_avatar` и `AvatarUpdate` не существуют.

- [ ] **Step 3: Добавить `AvatarUpdate` + endpoint в `routes/index.py`**

Рядом с другими Pydantic-моделями в `routes/index.py` (например, после `PlanCreate`):
```python
class AvatarUpdate(BaseModel):
    file_id: int
```

В любом месте файла (например, после `me`) добавить endpoint:
```python
@router.patch("/api/users/me/avatar")
def update_my_avatar(
    data: AvatarUpdate,
    current_user: dict = Depends(get_current_user_dep),
):
    """Set the current user's avatar to an existing file they uploaded."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT uploaded_by FROM files WHERE id = %s"), (data.file_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Файл не найден")
        if row[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Можно использовать только свой файл")
        cur.execute(
            q("UPDATE users SET avatar_file_id = %s WHERE id = %s"),
            (data.file_id, current_user["id"]),
        )
        conn.commit()
        return {"ok": True, "avatar_file_id": data.file_id, "avatar_url": _avatar_url(data.file_id)}
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_avatars.py -v`
Expected: PASS (5 тестов: 3 из Task 2 + 2 новых).

- [ ] **Step 5: Commit**

```bash
git add backend/routes/index.py backend/tests/test_avatars.py
git commit -m "feat(avatars-api): PATCH /api/users/me/avatar (validates uploaded_by)"
```

---

## Task 4: Chat members отдают avatar_url

**Files:**
- Modify: `backend/services/chat_service.py` — функция, собирающая `members[]` для каналов
- Test: `backend/tests/test_avatars.py` — 1 тест

- [ ] **Step 1: Найти, где members[] собираются в `chat_service.py`**

Прочитать `backend/services/chat_service.py`, найти SELECT с chat members (`SELECT u.id, u.username, u.name FROM channel_members cm`). Он в функции, которая собирает каналы с участниками для `GET /api/chat/channels`. Запомнить функцию и место.

- [ ] **Step 2: Добавить 1 тест**

Добавить в `backend/tests/test_avatars.py`:

```python
def test_chat_channels_members_include_avatar_url(seeded_avatars):
    # Сидируем минимальный канал + member, чтобы chat_service вернул members с avatar
    import services.chat_service as svc
    conn = psycopg2.connect(os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"))
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS channels (id SERIAL PRIMARY KEY, name TEXT, type TEXT, "
        "department_role TEXT, created_by INTEGER, created_at TIMESTAMPTZ DEFAULT now(), archived BOOLEAN DEFAULT false)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS channel_members (channel_id INTEGER, user_id INTEGER, "
        "joined_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (channel_id, user_id))"
    )
    cur.execute("INSERT INTO channels (name, type) VALUES ('G', 'general')")
    cur.execute("INSERT INTO channel_members (channel_id, user_id) VALUES (1, 1)")
    conn.commit()
    conn.close()

    # запросить каналы как alice — members должны включать avatar_url
    result = _run(svc.list_channels(current_user={"id": 1, "role": "manager"}))
    ch = result[0]
    member = next(m for m in ch["members"] if m["id"] == 1)
    assert member["avatar_url"] == "/api/files/1"
    assert member["avatar_file_id"] == 1
```

(Если `list_channels` имеет другую сигнатуру — прочитать и адаптировать.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_avatars.py::test_chat_channels_members_include_avatar_url -v`
Expected: FAIL — members не содержат avatar_url.

- [ ] **Step 4: Расширить members SELECT в `chat_service.py`**

Найденный SELECT (что-то вроде):
```sql
SELECT u.id, u.username, u.name FROM channel_members cm JOIN users u ON u.id = cm.user_id WHERE cm.channel_id = %s
```
Заменить на:
```sql
SELECT u.id, u.username, u.name, u.avatar_file_id FROM channel_members cm JOIN users u ON u.id = cm.user_id WHERE cm.channel_id = %s
```
В dict, формируемый для каждого member (обычно `{"id": r[0], "username": r[1], "name": r[2]}`), добавить:
```python
"avatar_file_id": r[3],
"avatar_url": _avatar_url(r[3]),
```

(`_avatar_url` импортировать из `routes.index` ИЛИ продублировать 1-строчник в `chat_service.py` — лучше импорт, чтобы DRY. Или вынести в `utils/avatar.py`. В плане — простой inline `f"/api/files/{fid}" if fid else None`, чтобы не плодить зависимость.)

- [ ] **Step 5: Run test to verify it passes + full suite**

Run: `cd backend && python -m pytest tests/test_avatars.py -v && python -m pytest -q`
Expected: PASS (6 avatar-тестов + 174 существующих = 180).

- [ ] **Step 6: Commit**

```bash
git add backend/services/chat_service.py backend/tests/test_avatars.py
git commit -m "feat(avatars-api): chat channel members include avatar_url"
```

---

## Task 5: Frontend — `Avatar.vue` компонент + тесты

**Files:**
- Create: `src/components/ui/Avatar.vue`
- Create: `src/components/ui/Avatar.test.ts`

- [ ] **Step 1: Создать `src/components/ui/Avatar.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  name: string
  src?: string | null
  size?: number
}>(), { size: 40 })

const initials = computed(() => {
  const parts = props.name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
})

const bgStyle = computed(() => {
  if (props.src) return {}
  let hash = 0
  for (const ch of props.name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  const hue = hash % 360
  return { backgroundColor: `hsl(${hue}, 55%, 50%)` }
})
</script>

<template>
  <img
    v-if="src"
    :src="src"
    :alt="name"
    class="rounded-full object-cover bg-slate-200"
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
  <div
    v-else
    class="rounded-full flex items-center justify-center text-white font-semibold select-none"
    :style="{ ...bgStyle, width: `${size}px`, height: `${size}px`, fontSize: `${size * 0.4}px` }"
  >{{ initials }}</div>
</template>
```

- [ ] **Step 2: Создать `src/components/ui/Avatar.test.ts`**

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Avatar from './Avatar.vue'

describe('Avatar', () => {
  it('renders <img> with src when provided', () => {
    const wrapper = mount(Avatar, { props: { name: 'Алиса', src: '/api/files/1', size: 40 } })
    expect(wrapper.find('img').attributes('src')).toBe('/api/files/1')
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('renders initials when no src', () => {
    const wrapper = mount(Avatar, { props: { name: 'Иван Петров', size: 40 } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('ИП')
  })

  it('deterministic color: same name → same hue', () => {
    // нельзя легко проверить hsl-цвет через jsdom, но проверим что bgStyle не пустой
    const w1 = mount(Avatar, { props: { name: 'Алиса' } })
    const w2 = mount(Avatar, { props: { name: 'Алиса' } })
    const div1 = w1.find('div')
    const div2 = w2.find('div')
    // оба имеют backgroundColor style
    expect(div1.attributes('style')).toContain('background-color')
    expect(div1.attributes('style')).toBe(div2.attributes('style'))
  })

  it('single name → first 2 letters', () => {
    const wrapper = mount(Avatar, { props: { name: 'Admin' } })
    expect(wrapper.text()).toBe('AD')
  })
})
```

- [ ] **Step 3: Run tests**

Run: `npm test -- Avatar`
Expected: PASS (4 теста).

- [ ] **Step 4: Run all fe tests + build**

Run: `npm test && npm run build`
Expected: 11 + 4 = **15** fe тестов PASS, build OK.

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/Avatar.vue src/components/ui/Avatar.test.ts
git commit -m "feat(avatars-fe): Avatar component (img or initials+HSL color) + tests"
```

---

## Task 6: `FileUploader` drag-drop

**Files:**
- Modify: `src/components/ui/FileUploader.vue`

- [ ] **Step 1: Переписать `src/components/ui/FileUploader.vue` с drag-drop**

Полная замена содержимого:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { filesApi } from '@/api/files'
import type { StoredFile } from '@/types/file'

const props = defineProps<{
  accept?: string
  maxSizeBytes?: number
}>()

const emit = defineEmits<{
  uploaded: [file: StoredFile]
  error: [message: string]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const isDragging = ref(false)

function openPicker() {
  inputRef.value?.click()
}

async function handleFile(file: File) {
  if (props.maxSizeBytes && file.size > props.maxSizeBytes) {
    emit('error', `Файл слишком большой (макс. ${Math.round(props.maxSizeBytes / 1024 / 1024)}MB)`)
    return
  }
  uploading.value = true
  try {
    const { data } = await filesApi.upload(file)
    emit('uploaded', data)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить файл'
    emit('error', detail)
  } finally {
    uploading.value = false
  }
}

function onChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) handleFile(file)
  target.value = ''
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) handleFile(file)
}
</script>

<template>
  <div
    class="file-uploader rounded-lg transition-colors"
    :class="{ 'bg-brand-50 ring-2 ring-brand-500 ring-inset': isDragging }"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="inputRef"
      type="file"
      class="hidden"
      :accept="accept"
      @change="onChange"
    />
    <slot :open="openPicker" :uploading="uploading" :is-dragging="isDragging">
      <button
        type="button"
        class="w-full rounded-md border border-dashed border-gray-300 px-4 py-3 text-sm text-gray-600 hover:border-brand-500 hover:text-brand-700"
        :disabled="uploading"
        @click="openPicker"
      >
        {{ uploading ? 'Загрузка…' : isDragging ? 'Отпустите, чтобы загрузить' : 'Выбрать или перетащить файл' }}
      </button>
    </slot>
  </div>
</template>
```

- [ ] **Step 2: Verify build + tests**

Run: `npm run build && npm test`
Expected: build ✓, 15 тестов PASS (без изменений — drag-drop проверяется ручным smoke).

- [ ] **Step 3: Commit**

```bash
git add src/components/ui/FileUploader.vue
git commit -m "feat(files-fe): FileUploader drag-and-drop zone (shared handleFile)"
```

---

## Task 7: `auth.ts` store — avatarUrl getter + updateAvatar

**Files:**
- Modify: `src/stores/auth.ts`
- Modify: `src/types/auth.ts` — `User` тип
- Modify: `src/api/auth.ts` (если есть) или `src/api/client.ts`

- [ ] **Step 1: Расширить `User` тип в `src/types/auth.ts`**

Прочитать текущий `User` интерфейс, добавить:
```typescript
avatar_file_id?: number | null
avatar_url?: string | null
```

- [ ] **Step 2: Добавить `avatarUrl` getter + `updateAvatar` в `src/stores/auth.ts`**

В `useAuthStore`, после `role` computed, добавить:
```typescript
const avatarUrl = computed(() => user.value?.avatar_url ?? null)

async function updateAvatar(fileId: number) {
  const { api } = await import('@/api/client')
  const { data } = await api.patch('/api/users/me/avatar', { file_id: fileId })
  if (user.value) {
    user.value = { ...user.value, avatar_file_id: fileId, avatar_url: data.avatar_url }
    localStorage.setItem('ksvrn_user', JSON.stringify(user.value))
  }
}
```

И в return добавить `avatarUrl, updateAvatar`:
```typescript
return { user, token, isAuthenticated, role, avatarUrl, login, fetchMe, logout, updateAvatar }
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: ✓.

- [ ] **Step 4: Commit**

```bash
git add src/stores/auth.ts src/types/auth.ts
git commit -m "feat(avatars-fe): auth store avatarUrl getter + updateAvatar action"
```

---

## Task 8: `ProfileView.vue` + `/profile` route

**Files:**
- Create: `src/views/ProfileView.vue`
- Modify: `src/router/index.ts`

- [ ] **Step 1: Создать `src/views/ProfileView.vue`**

```vue
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { toast } from 'vue-toastification'
import Avatar from '@/components/ui/Avatar.vue'
import FileUploader from '@/components/ui/FileUploader.vue'

const auth = useAuthStore()

async function onAvatarUploaded(file: { id: number }) {
  try {
    await auth.updateAvatar(file.id)
    toast.success('Аватар обновлён')
  } catch {
    toast.error('Не удалось обновить аватар')
  }
}
</script>

<template>
  <div class="max-w-md mx-auto py-8 px-4">
    <div class="card p-6 space-y-4">
      <div class="flex justify-center">
        <Avatar :name="auth.user?.name ?? '?'" :src="auth.avatarUrl" :size="120" />
      </div>
      <div class="text-center">
        <h1 class="text-xl font-semibold">{{ auth.user?.name }}</h1>
        <p class="text-sm text-slate-500">@{{ auth.user?.username }} · {{ auth.user?.role }}</p>
      </div>
      <FileUploader
        accept="image/*"
        :max-size-bytes="5 * 1024 * 1024"
        @uploaded="onAvatarUploaded"
        @error="(msg: string) => toast.error(msg)"
      >
        <template #default="{ open, uploading }">
          <button class="btn-primary w-full" :disabled="uploading" @click="open">
            {{ uploading ? 'Загрузка...' : 'Сменить фото' }}
          </button>
        </template>
      </FileUploader>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Добавить `/profile` route в `src/router/index.ts`**

В routes-массив, **вне** role-блоков (после `{ path: '/login', ... }`, перед role-блоками), добавить:
```typescript
  {
    path: '/profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { roles: ['admin', 'manager', 'employee', 'client'] },
  },
```

(Прочитать `guards.ts` чтобы убедиться, что `roles: ['admin','manager','employee','client']` пропустит любой auth-юзера. Если guard иначе трактует роли — адаптировать meta.)

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: ✓.

- [ ] **Step 4: Commit**

```bash
git add src/views/ProfileView.vue src/router/index.ts
git commit -m "feat(profile-fe): minimal /profile page with avatar upload"
```

---

## Task 9: Интеграция — ChatPanel (chat adapter)

**Files:**
- Modify: `src/types/chat.ts` — `Channel.members[].avatar_url`
- Modify: `src/composables/useChatAdapter.ts` — `users[].avatar`

- [ ] **Step 1: Расширить тип members в `src/types/chat.ts`**

В интерфейсе `Channel` найти `members?: { id: number; username: string; name: string }[]`, заменить на:
```typescript
members?: { id: number; username: string; name: string; avatar_url?: string | null; avatar_file_id?: number | null }[]
```

- [ ] **Step 2: В `src/composables/useChatAdapter.ts` добавить avatar в `toRoom.users`**

В `toRoom` функция, найти:
```typescript
users: (c.members ?? []).map((m) => ({ _id: String(m.id), username: m.name })),
```
Заменить на:
```typescript
users: (c.members ?? []).map((m) => ({
  _id: String(m.id),
  username: m.name,
  avatar: m.avatar_url ?? '',
})),
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: ✓.

- [ ] **Step 4: Commit**

```bash
git add src/types/chat.ts src/composables/useChatAdapter.ts
git commit -m "feat(avatars-fe): chat adapter passes avatar to vue-advanced-chat users[]"
```

---

## Task 10: Интеграция — AppSidebar + PersonnelView

**Files:**
- Modify: `src/components/sidebar/AppSidebar.vue`
- Modify: `src/views/admin/PersonnelView.vue`

- [ ] **Step 1: Прочитать текущий AppSidebar нижний блок + PersonnelView**

Run: `cat src/components/sidebar/AppSidebar.vue` (нижний блок, где username + LogOut).
Run: `cat src/views/admin/PersonnelView.vue` (найти, где рендерится имя юзера в таблице).

- [ ] **Step 2: В AppSidebar — аватар + ссылка «Профиль»**

В нижнем блоке (где сейчас `<div class="px-3 py-1 ...">{{ auth.user?.username }}</div>`), заменить на:
```vue
<div class="p-2 border-t border-slate-200">
  <RouterLink to="/profile" class="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-slate-100">
    <Avatar :name="auth.user?.name ?? '?'" :src="auth.avatarUrl" :size="32" class="shrink-0" />
    <div class="min-w-0 flex-1">
      <div class="text-xs font-medium truncate">{{ auth.user?.username }}</div>
      <div class="text-xs text-slate-500">Профиль</div>
    </div>
  </RouterLink>
  <button class="btn-ghost w-full justify-start text-sm" @click="auth.logout(); router.push('/login')">
    <LogOut :size="14" /> Выйти
  </button>
</div>
```

Добавить импорт `Avatar` вверху `<script setup>`:
```typescript
import Avatar from '@/components/ui/Avatar.vue'
```

- [ ] **Step 3: В PersonnelView — колонка аватара**

Прочитать таблицу PersonnelView. Перед колонкой имени (где рендерится `user.name`) добавить ячейку/Avatar:
```vue
<td class="px-3 py-2">
  <Avatar :name="user.name" :src="user.avatar_url" :size="32" />
</td>
```
И в header таблицы — пустую ячейку или иконку. Импортировать `Avatar`. (Точная правка — по прочитанной структуре файла.)

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: ✓.

- [ ] **Step 5: Commit**

```bash
git add src/components/sidebar/AppSidebar.vue src/views/admin/PersonnelView.vue
git commit -m "feat(avatars-fe): Avatar in sidebar (profile link) + PersonnelView column"
```

---

## Task 11: Финальная проверка

**Files:** none

- [ ] **Step 1: Full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: **180 passed** (174 + 6 avatar).

- [ ] **Step 2: Full frontend suite**

Run: `npm test`
Expected: **15 passed** (11 + 4 Avatar).

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: `✓ built`.

- [ ] **Step 4: Ручной smoke (пользователь)**

1. `/profile` — открывается, виден аватар (инициалы, если нет фото) + имя
2. Кликнуть «Сменить фото» → выбрать картинку → аватар обновился
3. Sidebar — аватар виден, клик → переход на /profile
4. Открыть чат — у участников есть аватар (VAC использует avatar_url или свой fallback)
5. PersonnelView (admin) — колонка с аватарами сотрудников

---

## Task 12: Деплой

- [ ] **Step 1: Backup БД**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'sudo -u postgres pg_dump hhb_b2b | gzip > /root/crmks_backup_$(date +%Y%m%d_%H%M%S).sql.gz && ls -lh /root/crmks_backup_*.sql.gz | tail -1'
```

- [ ] **Step 2: Push + pull**

```bash
git push origin main
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'cd /var/www/crmks && git checkout -- package-lock.json; git pull origin main'
```

- [ ] **Step 3: Backend restart (применит миграцию 011 при старте) + frontend build**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'cd /var/www/crmks && npm install && npm run build && systemctl restart crmks-api && sleep 4 && systemctl is-active crmks-api'
```

- [ ] **Step 4: Smoke**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'curl -s -o /dev/null -w "GET / → %{http_code}\n" https://crmdot.ru/ && \
   curl -s -o /dev/null -w "GET /api/auth/me (no auth) → %{http_code}\n" https://crmdot.ru/api/auth/me'
```
Expected: 200 + 401.

- [ ] **Step 5: Verify миграция применилась**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'sudo -u postgres psql -d hhb_b2b -c "\d users" | grep avatar'
```
Expected: строка с `avatar_file_id`.

---

## Self-Review (выполнено ассистентом)

**1. Spec coverage:**
- ✅ Миграция 011 → Task 1
- ✅ UserOut.avatar_url → Task 2
- ✅ me/list_users отдают avatar → Task 2
- ✅ PATCH /api/users/me/avatar → Task 3
- ✅ chat members avatar_url → Task 4
- ✅ Avatar.vue → Task 5
- ✅ ProfileView.vue + /profile → Task 8
- ✅ FileUploader drag-drop → Task 6
- ✅ auth.ts avatarUrl/updateAvatar → Task 7
- ✅ ChatPanel интеграция → Task 9
- ✅ Sidebar интеграция → Task 10
- ✅ PersonnelView интеграция → Task 10
- ✅ Финальный прогон → Task 11
- ✅ Деплой → Task 12

**2. Placeholder scan:** TODO/TBD нет. Все блоки кода конкретные. Шаги с «прочитать и адаптировать» (PersonnelView) — обоснованно (точная структура таблицы зависит от чтения файла, исполнитель сам адаптирует). ✅

**3. Type consistency:**
- `UserOut.avatar_file_id` + `avatar_url` (backend) ↔ `User.avatar_file_id?` + `avatar_url?` (frontend Task 7) — совпадает. ✅
- `_avatar_url` helper (Task 2) → используется в me/list_users (Task 2) + update_my_avatar (Task 3). ✅
- `update_my_avatar(data, current_user)` (Task 3) → тест передаёт `AvatarUpdate(file_id=1)`. ✅
- `auth.avatarUrl` getter (Task 7) → используется в ProfileView (Task 8) + sidebar (Task 10). ✅
- `users[].avatar` (Task 9) → VAC ожидает строку (avatar URL). ✅

Всё консистентно.

---

*План написан с любовью. 💕 Канарейка жива, паттерны подсмотрены, TDD соблюдён.*
