# Группа B: Удалить мёртвый PlansView + AuditView история визитов

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Удалить мёртвый `admin/PlansView.vue` (не подключён в роутере). (2) AuditView: сохранять чек-лист в notes (тег `audit`) + при входе загружать последнюю версию + показывать историю прошлых визитов.

**Architecture:**
- **PlansView:** просто удалить файл (он нигде не импортируется, в роутере `/admin/plans` указывает на `manager/PlanView.vue`, который уже работает с реальным фактом из `/api/kpi-plans`).
- **AuditView:** backend — добавить опциональный query-param `tag` в `GET /api/notes` (фильтр по тегу, хранится как JSON-строка в text колонке → фильтр на Python через `json.loads`). Frontend — при `onMounted` грузить `notes.list({tag: 'audit'})`, восстанавливать чек-лист из последней записи (парсить markdown `- [x]`/`- [ ]`), показывать блок «История визитов». Новая таблица НЕ нужна — notes с тегом `audit` полностью подходит.

**Tech Stack:** Python 3 (FastAPI, psycopg2), Vue 3 + TypeScript + Pinia, pytest.

**Принятые решения (из уточнения с заказчиком):**
- PlansView — удалить (мёртвый код).
- AuditView — чек-лист в notes + история визитов (а не отдельная таблица audit_reports).

---

## File Structure

| Файл | Ответственность | Статус |
|---|---|---|
| `src/views/admin/PlansView.vue` | Мёртвый код (не в роутере) | **Delete** |
| `backend/services/notes_service.py` | `list_notes` — добавить опц. параметр `tag`, фильтр по JSON-тегу | Modify |
| `backend/routes/notes.py` | `list_notes_endpoint` — пробросить query-param `tag` | Modify |
| `backend/tests/test_notes_tag_filter.py` | Тест: фильтр по тегу (возвращает только audit-заметки) | Create |
| `src/api/notes.ts` | `list` — принять опц. `{tag?: string}` | Modify |
| `src/stores/notes.ts` | `list` — пробросить params | Modify |
| `src/views/admin/AuditView.vue` | onMounted → загрузка последнего аудита + восстановление чек-листа + блок истории визитов; toast вместо ok/error | Modify |

---

## Task 1: Удалить мёртвый PlansView.vue

**Files:**
- Delete: `src/views/admin/PlansView.vue`

- [ ] **Step 1: Проверить что PlansView нигде не импортируется**

Run: `grep -rn "PlansView\|admin/PlansView" src/ --include='*.vue' --include='*.ts'`
Expected: 0 совпадений (только само имя файла не должно упоминаться в импортах/роутере).

Если есть совпадения — STOP, разобраться (разведка подтвердила: в `router/index.ts:20` маршрут `/admin/plans` ведёт на `@/views/manager/PlanView.vue`, НЕ на admin/PlansView).

- [ ] **Step 2: Удалить файл**

```bash
rm src/views/admin/PlansView.vue
```

- [ ] **Step 3: Smoke-проверка сборки**

Run: `npm run build`
Expected: success (если упало — значит где-то был импорт, вернуть файл и разобраться).

- [ ] **Step 4: Коммит**

```bash
git add src/views/admin/PlansView.vue
git commit -m "chore: remove dead admin/PlansView.vue (not in router, /admin/plans uses manager/PlanView)"
```

---

## Task 2: Backend — фильтр по тегу в `GET /api/notes`

**Files:**
- Modify: `backend/services/notes_service.py:12-44` (функция `list_notes`)
- Modify: `backend/routes/notes.py:26-30` (эндпоинт `list_notes_endpoint`)
- Test: `backend/tests/test_notes_tag_filter.py`

### Часть A: тест (RED)

- [ ] **Step 1: Создать тест-файл**

`backend/tests/test_notes_tag_filter.py`:
```python
"""Tests for GET /api/notes?tag=audit tag filtering."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.notes_service import list_notes


@pytest.fixture
def seeded_notes(db_conn, monkeypatch):
    """Seed notes with different tags and patch get_db to return test conn."""
    import psycopg2
    import services.notes_service as svc
    import os

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")

    # Ensure notes table exists
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS notes CASCADE")
    cur.execute(
        """
        CREATE TABLE notes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            title VARCHAR(300),
            content TEXT NOT NULL,
            color VARCHAR(20) DEFAULT 'yellow',
            pinned INTEGER DEFAULT 0,
            tags TEXT,
            client_id INTEGER,
            created_at VARCHAR(100),
            updated_at VARCHAR(100)
        )
        """
    )
    # Seed: 2 audit notes + 1 regular note for user_id=1
    cur.execute(
        """
        INSERT INTO notes (user_id, title, content, color, pinned, tags, created_at, updated_at) VALUES
        (1, 'Аудит 1', 'content1', 'yellow', 0, '["audit", "чемоданчик"]', '2026-07-01', '2026-07-01'),
        (1, 'Аудит 2', 'content2', 'yellow', 0, '["audit"]', '2026-07-02', '2026-07-02'),
        (1, 'Обычная заметка', 'content3', 'blue', 0, '[]', '2026-07-03', '2026-07-03')
        """
    )
    cur.close()

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(svc, "get_db", _test_get_db)
    return {"user_id": 1}


@pytest.mark.asyncio
async def test_list_notes_without_tag_returns_all(seeded_notes):
    """Without tag filter, all notes for the user are returned."""
    notes = await list_notes(current_user={"id": 1})
    assert len(notes) == 3


@pytest.mark.asyncio
async def test_list_notes_with_audit_tag_returns_only_audit(seeded_notes):
    """With tag='audit', only notes tagged 'audit' are returned."""
    notes = await list_notes(current_user={"id": 1}, tag="audit")
    assert len(notes) == 2
    titles = [n["title"] for n in notes]
    assert "Аудит 1" in titles
    assert "Аудит 2" in titles
    assert "Обычная заметка" not in titles


@pytest.mark.asyncio
async def test_list_notes_with_unknown_tag_returns_empty(seeded_notes):
    """With a tag that no note has, returns empty list."""
    notes = await list_notes(current_user={"id": 1}, tag="nonexistent")
    assert notes == []
```

- [ ] **Step 2: Прогнать — должен упасть (параметра `tag` нет)**

Run: `cd backend && python -m pytest tests/test_notes_tag_filter.py -v`
Expected: FAIL — `list_notes() got an unexpected keyword argument 'tag'`.

### Часть B: реализация (GREEN)

- [ ] **Step 3: Добавить параметр `tag` в `list_notes`**

В `backend/services/notes_service.py`, функция `list_notes` (строки 12-44). Заменить сигнатуру + добавить фильтр на Python (tags хранится как JSON-строка в text колонке, поэтому фильтр после выборки):

```python
async def list_notes(
    current_user: Dict[str, Any],
    tag: str | None = None,
) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q("""
        SELECT id, user_id, title, content, color, pinned, tags, client_id, created_at, updated_at
        FROM notes
        WHERE user_id = %s
        ORDER BY pinned DESC, updated_at DESC
        """),
        (current_user["id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    result = [
        {
            "id": r[0],
            "user_id": r[1],
            "title": r[2],
            "content": r[3],
            "color": r[4] or "yellow",
            "pinned": bool(r[5]),
            "tags": json.loads(r[6]) if r[6] else [],
            "client_id": r[7],
            "created_at": r[8] or "",
            "updated_at": r[9] or "",
        }
        for r in rows
    ]

    # Optional tag filter (tags stored as JSON string in text column).
    if tag:
        result = [n for n in result if tag in n["tags"]]

    return result
```

(Только сигнатура добавила `tag: str | None = None` + блок `if tag:` в конце. Остальное — без изменений.)

- [ ] **Step 4: Пробросить `tag` в эндпоинте**

В `backend/routes/notes.py`, заменить эндпоинт `list_notes_endpoint` (строки 26-30):

```python
from typing import Any, Dict, Optional

@router.get("/api/notes")
async def list_notes_endpoint(
    tag: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_notes(current_user=current_user, tag=tag)
```

(Добавлен query-param `tag: Optional[str] = None` и проброс в `list_notes`.)

- [ ] **Step 5: Прогнать тесты — GREEN**

Run: `cd backend && python -m pytest tests/test_notes_tag_filter.py -v`
Expected: 3 passed.

- [ ] **Step 6: Полный набор**

Run: `cd backend && python -m pytest -q`
Expected: все зелёные (94 + 3 новых = 97).

- [ ] **Step 7: Коммит**

```bash
git add backend/services/notes_service.py backend/routes/notes.py backend/tests/test_notes_tag_filter.py
git commit -m "feat(notes): add optional tag filter to GET /api/notes?tag=audit"
```

---

## Task 3: Frontend — api/stores notes поддерживают tag-фильтр

**Files:**
- Modify: `src/api/notes.ts`
- Modify: `src/stores/notes.ts`

- [ ] **Step 1: Прочитать текущие файлы**

Run: `cat src/api/notes.ts src/stores/notes.ts`

- [ ] **Step 2: Добавить params в `notesApi.list`**

В `src/api/notes.ts`, заменить `list`:

```ts
list: (params?: { tag?: string }) =>
  api.get<Note[]>('/api/notes', { params }),
```

(Добавлен опц. параметр `params` + передача в `{ params }` axios — axios сериализует в `?tag=audit`.)

- [ ] **Step 3: Пробросить params в `notes.list` store**

В `src/stores/notes.ts`, функция `list` (примерно строки 8-14). Добавить опц. параметр:

```ts
async function list(params?: { tag?: string }) {
  const { data } = await notesApi.list(params)
  items.value = data
}
```

(Только добавился параметр `params` и его проброс. Остальное без изменений.)

- [ ] **Step 4: Smoke-проверка**

Run: `npm run build`
Expected: success.

- [ ] **Step 5: Коммит**

```bash
git add src/api/notes.ts src/stores/notes.ts
git commit -m "feat(notes-fe): support tag filter in api/stores"
```

---

## Task 4: AuditView — загрузка последнего аудита + восстановление чек-листа

**Files:**
- Modify: `src/views/admin/AuditView.vue`

Это самая содержательная правка. Добавить:
1. `onMounted` → `notes.list({tag: 'audit'})` → взять первую (последнюю по updated_at) запись → восстановить чек-лист + reportText из `content`.
2. Парсер markdown чек-листа: из строк `- [x] Пункт` / `- [ ] Пункт` → массив `{item, done}`.
3. Toast (из волны 1) вместо `ok`/`error` текстовых сообщений.
4. Блок «История визитов» (список прошлых аудитов с датой + клик для загрузки).

- [ ] **Step 1: Добавить импорты + onMounted + loadLastAudit**

В `<script setup>` AuditView.vue (после строки 4 `const notes = useNotesStore()`), добавить импорты и логику загрузки. Полный новый `<script setup>`:

```ts
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useNotesStore } from '@/stores/notes'
import { toast } from '@/plugins/toast'
import type { Note } from '@/types/note'

const notes = useNotesStore()

function normalizeBaseUrl(v: string | undefined) {
  if (!v) return ''
  return v.endsWith('/') ? v.slice(0, -1) : v
}

const apiBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL as string | undefined)

const bitrixWebhookUrl = computed(() => (apiBaseUrl ? `${apiBaseUrl}/api/webhooks/bitrix` : '/api/webhooks/bitrix'))
const bitrixTelephonyWebhookUrl = computed(() => (apiBaseUrl ? `${apiBaseUrl}/api/webhooks/bitrix/telephony` : '/api/webhooks/bitrix/telephony'))
const oneCWebhookUrl = computed(() => (apiBaseUrl ? `${apiBaseUrl}/api/webhooks/1c` : '/api/webhooks/1c'))

async function copyToClipboard(text: string) {
  await navigator.clipboard.writeText(text)
}

interface ChecklistItem { item: string; done: boolean }

const DEFAULT_CHECKLIST: ChecklistItem[] = [
  { item: 'Чемоданчик с образцами HHB', done: false },
  { item: 'Технические паспорта подшипников', done: false },
  { item: 'Конкурентные образцы (SKF, CRAFT)', done: false },
  { item: 'Планшет с презентацией', done: false },
  { item: 'Визитки и каталоги', done: false },
]

const checklist = ref<ChecklistItem[]>(DEFAULT_CHECKLIST.map((c) => ({ ...c })))
const reportText = ref('')
const loading = ref(false)
const history = ref<Note[]>([])

const checklistMarkdown = computed(() => {
  return checklist.value
    .map((c) => `- [${c.done ? 'x' : ' '}] ${c.item}`)
    .join('\n')
})

/** Parse markdown checklist (- [x] item / - [ ] item) into ChecklistItem[]. */
function parseChecklistFromContent(content: string): { checklist: ChecklistItem[]; report: string } {
  const lines = content.split('\n')
  const parsedItems: ChecklistItem[] = []
  let reportLines: string[] = []
  let inReport = false

  for (const line of lines) {
    const m = line.match(/^- \[([x ])\] (.+)$/)
    if (m && !inReport) {
      parsedItems.push({ item: m[2].trim(), done: m[1] === 'x' })
    } else if (line.startsWith('### Результат визита')) {
      inReport = true
    } else if (inReport) {
      reportLines.push(line)
    }
  }
  // Clean report: drop empty/placeholder lines
  const report = reportLines.join('\n').replace(/^_—_$/, '').trim()
  return { checklist: parsedItems, report }
}

/** Merge parsed items into default checklist (preserve new default items not in history). */
function mergeChecklist(parsed: ChecklistItem[]): ChecklistItem[] {
  return DEFAULT_CHECKLIST.map((d) => {
    const found = parsed.find((p) => p.item.toLowerCase() === d.item.toLowerCase())
    return found ? { item: d.item, done: found.done } : { ...d }
  })
}

async function loadHistory() {
  try {
    await notes.list({ tag: 'audit' })
    history.value = notes.items
    // Restore last audit into the form
    if (history.value.length > 0) {
      const last = history.value[0] // list_notes orders by updated_at DESC
      const { checklist: parsed, report } = parseChecklistFromContent(last.content)
      if (parsed.length > 0) {
        checklist.value = mergeChecklist(parsed)
      }
      reportText.value = report
    }
  } catch {
    toast.error('Не удалось загрузить историю аудитов')
  }
}

function loadAudit(n: Note) {
  const { checklist: parsed, report } = parseChecklistFromContent(n.content)
  if (parsed.length > 0) {
    checklist.value = mergeChecklist(parsed)
  }
  reportText.value = report
}

async function saveReport() {
  loading.value = true
  try {
    const now = new Date()
    const title = `Аудит: ${now.toLocaleDateString('ru-RU')}`

    const content = [
      `### Чек-лист аудита`,
      checklistMarkdown.value,
      ``,
      `### Результат визита`,
      reportText.value || '_—_',
    ].join('\n')

    await notes.create({
      title,
      content,
      color: 'yellow',
      pinned: false,
      tags: ['audit', 'чемоданчик'],
    })

    reportText.value = ''
    toast.success('Отчёт аудита сохранён')
    await loadHistory() // refresh history list
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || e?.message || 'Ошибка сохранения')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadHistory()
})
</script>
```

**Ключевые изменения:**
- `DEFAULT_CHECKLIST` теперь с `done: false` (раньше 3 из 5 были `true` — это вводило в заблуждение; теперь по умолчанию все сняты, реальные состояния восстанавливаются из истории).
- `parseChecklistFromContent` — парсер markdown `- [x]`/`- [ ]` + секции «Результат визита».
- `mergeChecklist` — мёрджит распарсенное в дефолтный список (сохраняет новые пункты, которых не было в истории).
- `loadHistory` — грузит `notes.list({tag:'audit'})`, восстанавливает последний аудит в форму.
- `loadAudit(n)` — клик по элементу истории загружает его в форму.
- `saveReport` — после сохранения обновляет историю + toast.success.
- `onMounted` → `loadHistory()`.

- [ ] **Step 2: Добавить блок «История визитов» в template**

В `<template>`, после блока чек-листа + результата (после строки 110 `</div>` закрывающего grid), перед блоком вебхуков (строка 112), вставить:

```vue
    <!-- История визитов -->
    <div v-if="history.length > 0" class="card p-5 space-y-3">
      <div class="text-xs font-bold text-neutral-500 uppercase mb-2">История визитов</div>
      <div class="divide-y divide-slate-100">
        <button
          v-for="h in history"
          :key="h.id"
          class="w-full text-left p-3 rounded-xl hover:bg-slate-50 transition flex items-center justify-between gap-3"
          @click="loadAudit(h)"
        >
          <div>
            <div class="text-sm font-semibold text-neutral-800">{{ h.title }}</div>
            <div class="text-xs text-neutral-500 mt-0.5 line-clamp-2">{{ h.content.split('\n').filter((l: string) => !l.startsWith('- [') && !l.startsWith('###')).join(' ').slice(0, 120) || '—' }}</div>
          </div>
          <div class="text-xs text-neutral-400 shrink-0">{{ (h.updated_at || h.created_at || '').slice(0, 10) }}</div>
        </button>
      </div>
    </div>
```

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Коммит**

```bash
git add src/views/admin/AuditView.vue
git commit -m "feat(audit): load last checklist from notes + visit history + toast"
```

---

## Task 5: Деплой + проверка

**Files:** — (операционный)

- [ ] **Step 1: Полный набор тестов**

Run:
```bash
cd backend && python -m pytest -q   # expect 97 passed
cd .. && npm run build              # success
npm run test                        # 3 passed (useConfirm)
```

- [ ] **Step 2: Деплой backend + frontend на CRM**

```bash
# Backend (tag filter) — pull + restart
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 "cd /var/www/crmks && git pull origin main && systemctl restart crmks-api"

# Frontend (AuditView + deleted PlansView)
scp -r -i ~/.ssh/kyk_server_key dist/* root@72.56.246.21:/var/www/crmks/dist/
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 "nginx -s reload"
```

- [ ] **Step 3: Live-проверка на https://crmdot.ru**

```bash
# 1. notes tag filter works
curl -s "https://crmdot.ru/api/notes?tag=audit" -H "Authorization: Bearer <token>" | python -m json.tool | head -20

# 2. В UI: AuditView → отметить чек-лист → Сохранить → перезагрузить → состояние должно восстановиться
```

- [ ] **Step 4: Merge в main**

```bash
git checkout main
git merge feat/group-b-plans-audit --no-ff -m "Merge Group B: remove dead PlansView + AuditView checklist persistence + history"
git push origin main
```

---

## Self-Review (выполнено автором плана)

**1. Spec coverage:**
- Удалить PlansView → Task 1. ✓
- AuditView чек-лист в notes + загрузка → Task 4 (onMounted + parseChecklistFromContent + loadHistory). ✓
- AuditView история визитов → Task 4 (блок history + loadAudit). ✓
- Backend фильтр по тегу → Task 2 (list_notes tag param + тесты). ✓
- Frontend api/stores проброс → Task 3. ✓
- Деплой → Task 5. ✓

**2. Placeholder scan:** нет TBD/TODO; код в шагах — финальный; парсер markdown дан полностью.

**3. Type consistency:**
- `list_notes(current_user, tag=None)` — сигнатура едина в Task 2 (определение) и Task 2 Step 4 (роут).
- `notesApi.list(params?: {tag?})` — едино в Task 3 Step 2 (api) и Step 3 (store).
- `ChecklistItem` интерфейс — определён и использован в `checklist`, `DEFAULT_CHECKLIST`, `parseChecklistFromContent`, `mergeChecklist`.
- `tag='audit'` — единое имя тега во всём плане.

**Риски (явно):**
- **Парсинг markdown:** `parseChecklistFromContent` рассчитан на формат, который генерирует текущий `saveReport` (`### Чек-лист аудита` + `- [x] item` + `### Результат визита`). Если в старых записях формат отличается — парсер вернёт пустой checklist, и сработает `DEFAULT_CHECKLIST` (все false). Это безопасный fallback.
- **Обратная совместимость:** старые audit-записи (если есть) с markdown продолжат парситься. Новые записи используют тот же формат → корректно восстановятся.
- **DEFAULT_CHECKLIST с done:false:** раньше 3 из 5 были `true` по умолчанию. Теперь все `false` — это правильно (реальное состояние должно приходить из истории, а не из захардкоженных предположений).
- **`pytest.mark.asyncio`:** тесты async. Если `pytest-asyncio` не установлен — проверить `backend/requirements.txt`; если нет, добавить `pytest-asyncio` или запустить через `asyncio.run()` (есть уже в других тестах). Проверить при выполнении Task 2.
