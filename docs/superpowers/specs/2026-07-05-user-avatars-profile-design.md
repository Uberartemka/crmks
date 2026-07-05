# CRM: Аватарки пользователей + минимальный ЛК — Design

**Дата:** 2026-07-05
**Статус:** Approved (пользователь одобрил дизайн 2026-07-05)
**Автор совместной сессии:** пользователь + ассистент
**Связанные документы:** `2026-07-04-chat-attachments-design.md` (файловый сервис — фундамент), `2026-07-05-chat-panel-relocation-design.md` (чат в правой панели)

## Контекст и проблема

В CRM **нет аватарок пользователей** вообще — ни в БД (`users` без avatar-колонки), ни в UI. Командный чат показывает голые имена, sidebar — только username, PersonnelView — таблицу без лиц. Это снижает узнаваемость и «человечность» интерфейса.

Файловый сервис (Подсистема II) **уже готов и на проде** (`POST /api/files`, thumbnail для картинок). Значит, фундамент для аватарок существует — осталось привязать.

Параллельно: **личного кабинета нет** (`/profile`), юзеру некуда зайти, чтобы управлять собой. Делаем минимальный ЛК = аватар + имя + смена фото. Это закроет базовую потребность и станет заделом под будущий полный профиль.

### Что в дизайн НЕ входит (явный YAGNI для этой фазы)

- **Drag-вложения в чат** (Подсистема II для chat, `messages.attachment_id`) — отдельная фаза, отложена. Здесь только drag в `FileUploader` (компонентно), для ЛК.
- **Смена пароля / email / телефона** — это полный профиль, не сейчас. Только аватар.
- **Удаление старого аватара при смене** — orphan-файлы копятся, но на 24GB это пренебрежимо (см. спеку файлового сервиса).
- **Серверная генерация аватарок** (DiceBear и т.п.) — fallback делаем на фронте (инициалы + цвет), без внешних запросов.
- **Кроппинг/ресайз на клиенте** — thumbnail уже генерируется на сервере (Pillow). Клиент грузит как есть.
- **Групповые аватарки каналов** — только персональные.

---

## Решения (из brainstorming с пользователем)

1. **Fallback при отсутствии аватарки** — инициалы из `name` + детерминированный цвет (HSL hue из хеша name). Без внешних зависимостей, всегда работает.
2. **Минимальный ЛК** (`/profile`) — только аватар + имя + кнопка «сменить фото». Не полный профиль.
3. **Готовые решения подсмотрены, не скопированы**: `vue3-avatar` (GitHub) дал API-паттерн (name + src + size), TailwindFlex profile form дал layout-идею. Своё实现: 1 компонент `Avatar.vue` (~30 строк) вместо npm-зависимости.
4. **Аватарки видны везде**: чат, sidebar, персонал, ЛК.

---

## Архитектура

```
Данные:
  users.avatar_file_id BIGINT NULL → files.id (ON DELETE SET NULL)
  UserOut.avatar_url = avatar_file_id ? `/api/files/{id}` : null   (вычисляется при отдаче)

Загрузка (ЛК):
  /profile → FileUploader (drag-drop) → filesApi.upload(file) → {id}
           → PATCH /api/users/me/avatar {file_id}
           → backend UPDATE users.avatar_file_id, returns UserOut
           → auth store обновляется → Avatar реактивно перерисуется

Отображение (4 места):
  ChatPanel: vue-advanced-chat users[].avatar (через useChatAdapter)
  AppSidebar: <Avatar> возле username (внизу)
  PersonnelView: <Avatar> колонка перед именем
  ProfileView: <Avatar :size="120"> в карточке
```

---

## Backend изменения

### 1. Миграция 011

```sql
-- Migration 011: user avatars.
-- Idempotent (information_schema guard). Assumes users + files tables exist.
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

### 2. `schemas/auth.py` — расширить `UserOut`

```python
class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    avatar_file_id: Optional[int] = None
    avatar_url: Optional[str] = None  # /api/files/{id} или None
```

### 3. Helper: вычисление `avatar_url`

В `routes/index.py` (или утилите) — функция, которая по `avatar_file_id` строит URL:
```python
def _avatar_url(avatar_file_id: int | None) -> str | None:
    return f"/api/files/{avatar_file_id}" if avatar_file_id else None
```
Применять в `me`, `list_users`, и любых других местах, отдающих `UserOut`.

### 4. `GET /api/auth/me` и `GET /api/users` — отдавать avatar_file_id + avatar_url

`me` (routes/index.py:87): SELECT добавить `avatar_file_id`, в ответ добавить оба поля.
`list_users` (routes/index.py:92): SELECT добавить `u.avatar_file_id`, в каждый элемент списка — `avatar_file_id` + `avatar_url`.

### 5. `PATCH /api/users/me/avatar` — новый endpoint

```python
class AvatarUpdate(BaseModel):
    file_id: int

@router.patch("/api/users/me/avatar")
def update_my_avatar(
    data: AvatarUpdate,
    current_user: dict = Depends(get_current_user_dep),
):
    # Проверяем: файл существует и принадлежит текущему юзеру
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            q("SELECT uploaded_by FROM files WHERE id = %s"),
            (data.file_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Файл не найден")
        if row[0] != current_user["id"]:
            raise HTTPException(403, "Можно использовать только свой файл")
        cur.execute(
            q("UPDATE users SET avatar_file_id = %s WHERE id = %s"),
            (data.file_id, current_user["id"]),
        )
        conn.commit()
        return {"ok": True, "avatar_file_id": data.file_id, "avatar_url": _avatar_url(data.file_id)}
    finally:
        conn.close()
```

**Почему проверка `uploaded_by == current_user["id"]`**: нельзя привязать чужой файл как свой аватар (защита). Юзер сначала грузит файл через `POST /api/files` (где становится `uploaded_by`), потом привязывает.

### 6. Chat members — `avatar_url` в `members[]`

`GET /api/chat/channels` отдаёт `members: [{id, username, name}]`. Расширить: добавить `avatar_file_id` и `avatar_url`. Соответственно JOIN с files ИЛИ вычислять через `_avatar_url()` в Python.

В `chat_service.py` функция, собирающая каналы с members — добавить SELECT `u.avatar_file_id` для members, в dict members — `avatar_file_id` + `avatar_url`.

---

## Frontend изменения

### 1. `src/components/ui/Avatar.vue` (новый, мини)

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

### 2. `src/views/ProfileView.vue` (новый)

Минимальный ЛК: аватар + имя + кнопка смены через `FileUploader` (с drag-drop).

```vue
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { filesApi } from '@/api/files'
import { toast } from 'vue-toastification'
import Avatar from '@/components/ui/Avatar.vue'
import FileUploader from '@/components/ui/FileUploader.vue'

const auth = useAuthStore()

async function onAvatarUploaded(file: { id: number }) {
  try {
    await auth.updateAvatar(file.id)  // PATCH /api/users/me/avatar
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
        @error="(msg) => toast.error(msg)"
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

### 3. `src/stores/auth.ts` — `avatarUrl` getter + `updateAvatar`

```typescript
const avatarUrl = computed(() =>
  authUser.value?.avatar_url ?? null
)

async function updateAvatar(fileId: number) {
  const { data } = await api.patch('/api/users/me/avatar', { file_id: fileId })
  // обновляем локальный юзер-объект
  if (authUser.value) {
    authUser.value = { ...authUser.value, avatar_url: data.avatar_url, avatar_file_id: fileId }
  }
}
```

(Или fetch `/api/auth/me` заново после patch — надёжнее, но лишний запрос. Первый вариант быстрее.)

### 4. `src/components/ui/FileUploader.vue` — drag-drop зона

Расширить существующий компонент: обернуть в drop-zone, добавить `isDragging` ref, `onDrop` хендлер (берёт первый файл из `event.dataTransfer.files`, валидирует, грузит).

```vue
<script setup lang="ts">
// ...существующее...
const isDragging = ref(false)

function onDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) handleFile(file)  // вынести логику из onChange в handleFile
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
    <!-- существующий input + slot -->
  </div>
</template>
```

(Рефакторинг: вынести общую логику загрузки из `onChange` в функцию `handleFile(file: File)`, чтобы её звали и onChange, и onDrop.)

### 5. ChatPanel — `useChatAdapter.ts` добавить avatar в users

```typescript
users: (c.members ?? []).map((m) => ({
  _id: String(m.id),
  username: m.name,
  avatar: m.avatar_url ?? '',  // VAC: пустая строка → VAC рисует свой fallback
})),
```

(Расширить тип `ChannelWithMembers.members[]` полем `avatar_url`.)

### 6. AppSidebar — аватар возле username

В нижнем блоке sidebar (где сейчас username + кнопка выхода):
```vue
<div class="p-2 border-t border-slate-200">
  <div class="flex items-center gap-2 px-3 py-2">
    <Avatar :name="auth.user?.name ?? '?'" :src="auth.avatarUrl" :size="32" class="shrink-0" />
    <div class="min-w-0 flex-1">
      <div class="text-xs font-medium truncate">{{ auth.user?.username }}</div>
      <RouterLink to="/profile" class="text-xs text-slate-500 hover:underline">Профиль</RouterLink>
    </div>
  </div>
  <button class="btn-ghost w-full justify-start text-sm" @click="auth.logout(); router.push('/login')">
    <LogOut :size="14" /> Выйти
  </button>
</div>
```

### 7. PersonnelView — колонка с аватаром

Перед колонкой имени — `<Avatar :size="32">`. Конкретная правка зависит от текущей структуры PersonnelView (прочитать при реализации).

### 8. Router — `/profile`

В `src/router/index.ts` добавить вне role-блоков (доступ всем auth):
```typescript
{ path: '/profile', component: () => import('@/views/ProfileView.vue'), meta: { roles: ['admin','manager','employee','client'] } },
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| Нет аватарки | `Avatar.vue` рисует инициалы + цвет (детерминированно из name) |
| Файл аватарки удалён (admin удалил file) | FK `ON DELETE SET NULL` → `avatar_file_id` NULL → `avatar_url` null → инициалы |
| Загрузил не-картинку как аватар | `accept="image/*"` на клиенте + можно добавить серверную проверку `is_image` в PATCH (YAGNI сейчас — file_service принимает любой тип) |
| Сменил аватар — старый orphan | Не удаляем (24GB, пренебрежимо). Future: cleanup-job. |
| Client-юзер | Может иметь аватар (видит в sidebar/своём /profile). PATCH endpoint доступен всем auth. |
| Одинаковые имена → одинаковый цвет | Принимаемо (hue из хеша, у двух "Иван Петров" будет один цвет — узнаваемо по контексту) |
| VAC avatar пустая строка | VAC рисует свой fallback (не наш Avatar.vue). Чтобы наш fallback работал в чате — нужно передавать thumbnailUrl, тогда VAC покажет картинку. Для строгости — проверим на smoke. |

---

## Тестирование

### Backend (+5)

| # | Тест | Что проверяет |
|---|---|---|
| 1 | `test_me_returns_avatar_url_when_set` | есть avatar_file_id → avatar_url заполнен |
| 2 | `test_me_avatar_url_null_when_no_avatar` | нет аватара → null |
| 3 | `test_update_my_avatar_sets_file_id` | PATCH устанавливает, возвращает avatar_url |
| 4 | `test_update_my_avatar_other_users_file_403` | чужой файл → 403 |
| 5 | `test_chat_channels_members_include_avatar_url` | members[] содержат avatar_url |

### Frontend (+3)

| # | Тест | Что проверяет |
|---|---|---|
| 6 | `Avatar` рендерит `<img>` при наличии src |
| 7 | `Avatar` рендерит инициалы при отсутствии src |
| 8 | `Avatar` детерминированный цвет (один name → один hue) |

Ожидаемый счёт: 174 → 179 backend (+5), 11 → 14 frontend (+3).

---

## Деплой

- **Backup БД** (миграция 011 меняет схему users).
- Push → pull → backend restart (миграция применится при старте).
- Frontend rebuild.
- Smoke: открыть `/profile`, загрузить картинку → аватар появился в sidebar/чате.

---

## Риски и компромиссы

- **`avatar_url` вычисляется в Python при каждом запросе** — дёшево (форматирование строки), но при больших списках пользователей можно закешировать. YAGNI сейчас.
- **Chat members JOIN с files** — расширяет запрос `GET /api/chat/channels`. На объёмах CRM — пренебрежимо.
- **Client-юзер видит свой аватар** — да, но `PATCH /api/users/me/avatar` требует, чтобы файл был `uploaded_by` текущего юзера. Client может грузить файлы (POST /api/files не имеет role-gate сейчас — это вопрос; стоит проверить, что clients могут).
- **VAC avatar fallback** — VAC имеет свой fallback (другой стиль инициалов). Чтобы консистентно с нашим `Avatar.vue`, передаём `avatar_url` ИЛИ thumbnailUrl; если пусто — VAC рисует своё. Принимаемо (в чате узнаваемость по имени + любой аватар ок).

---

*Спека написана с любовью. 💕 Канарейка жива, паттерны подсмотрены у открытых проектов (но не скопированы — свой实现 под наш стек).*
