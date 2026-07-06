# CRM: Вложения в чат (Подсистема II — интеграция) — Design

**Дата:** 2026-07-07
**Статус:** Approved (пользователь одобрил дизайн 2026-07-07)
**Автор совместной сессии:** пользователь + ассистент
**Связанные документы:** `2026-07-04-chat-attachments-design.md` (базовый файловый сервис, родительская спека), `2026-07-04-chat-messaging-design.md` (чат), `2026-07-04-chat-reply-design.md` (reply), `2026-07-05-user-avatars-profile-design.md` (паттерн публичного endpoint'а)

---

## Контекст и проблема

Базовый файловый сервис (Подсистема II) готов: таблица `files` (миграция 010),
`services/file_service.py` (`save_upload`/`get_file`/thumbnails), `routes/files.py`
(`POST /api/files`, `GET /api/files/{id}`, `GET /api/files/{id}/thumbnail`), frontend
`filesApi` + `StoredFile` + `FileUploader`/`FilePreview`. Сервис уже используется
аватарками (`users.avatar_file_id`, миграция 011, публичный `/api/avatars/{id}`).

Но **чат не умеет прикреплять файлы к сообщениям.** Колонки `messages.attachment_id`
нет, поля `file` в адаптере VAC нет, `:show-files="false"`. Это «фаза 2» родительской
спеки, которую сознательно отложили. Сейчас — её время.

Цель: дать staff-юзерам возможность прикреплять PDF/фото/документы к сообщениям в
ChatPanel и видеть их в ленте чата (превью для картинок, иконку-карточку для остальных).

### Что в дизайн НЕ входит (явный YAGNI для этой фазы)

- **Cleanup-job для orphan-файлов.** Eager upload (см. ниже) создаёт файлы сразу,
  даже если юзер не отправил сообщение. Orphan-файлы копятся. Cleanup — отдельная
  задача (уже в known issues хэндоффа). Здесь — фиксируем как trade-off, не решаем.
- **Ленивая привязка / drag нескольких файлов сразу.** Один файл на сообщение
  (как требует VAC-контракт `message.file` — single object). Множественные вложения —
  когда выяснится потребность.
- **Рефактор `/api/avatars/{id}` в `routes/files.py`.** Публичный avatar-endpoint
  живёт в `routes/index.py`, новые публичные attachment-endpoint'ы пойдут в
  `routes/files.py`. Это минорная несогласованность (фиксируется в trade-offs),
  переносить аватары — отдельный scope, не трогаем.
- **Мультитенантность / RLS для вложений.** Не реализована в проекте вообще.
  Изоляция — через `uploaded_by` owner-check при отправке + gate при раздаче
  (см. ниже). Сознательное решение, как и в родительской спеке.
- **Физическое удаление файла при удалении сообщения.** Soft-delete сообщения
  (существующий паттерн) → gate по `deleted_at IS NULL` скрывает вложение.
  Hard-delete файла — `ON DELETE SET NULL` (как `reply_to_id`).
- **Дедупликация.** `sha256` уже пишется, дедуп не делается (наследие родительской спеки).
- **Изменение лимитов/MIME-whitelist.** 100MB, существующий whitelist — переиспользуем
  без изменений (attack surface уже закрыт в `save_upload`).

---

## Решения (из brainstorming с пользователем)

1. **Рендеринг вложений — публичный endpoint** (как аватарки). Причина: VAC рендерит
   картинки через `<img src>`/CSS `background-image`, которые **не могут** отправить
   Bearer-токен → приватные `/api/files/{id}` (с owner-check) для `<img>` не работают
   (401). Это тот самый затык, который уже решён для аватарок через `/api/avatars/{id}`.
   Делаем аналог `/api/chat-attachments/{id}` — публичный, но **gate'нутый**: отдаёт
   только файлы, привязанные к **не-удалённому** сообщению (`EXISTS` на `messages`).
   Произвольные приватные файлы через него не скачать. **Пользователь сознательно
   принял** минус (id перечислимы — BIGSERIAL, любой со знанием id скачает
   attachment-файл). Для CRM с внутренними staff-юзерами приемлемо.

2. **Загрузка — VAC native upload + eager.** Включаем `:show-files="true"`,
   вешаем `@upload-file`. Юзер жмёт скрепку/drag → VAC эмитит `{file, roomId}` →
   грузим через `filesApi.upload(file)` **сразу** (eager) → сохраняем
   `pendingAttachment[roomId] = {id, meta}` → при `send-message` шлём `attachment_id`.
   Плюс: нативная UI VAC (скрепка, drag, превью вложения в поле ввода). Минус: orphan-
   файлы если не отправил (см. YAGNI выше).

3. **Невалидный attachment_id при send — graceful drop** (как `reply_to_id`).
   Чужой/несуществующий/удалённый `attachment_id` → обнуляем, **текст сообщения не
   теряем**. Паттерн уже отработан в reply (`chat_service.py:263-273`). Не роняем send
   ради вложения.

4. **FK `ON DELETE SET NULL`.** `messages.attachment_id REFERENCES files(id) ON DELETE
   SET NULL` — как `reply_to_id` и `users.avatar_file_id`. Файл удалили → сообщение
   живёт, просто без вложения.

5. **Reuse одного файла разрешён.** Один `attachment_id` можно привязать к нескольким
   сообщениям — owner-check проверяет только `uploaded_by == user.id`, а не «уже
   использован ли файл». Это **фича** (переслать один загруженный PDF в несколько
   каналов без re-upload), не баг. Следствие для будущего cleanup'а: orphan-detection
   должен считать `COUNT(messages WHERE attachment_id = file.id) = 0`, а не `EXISTS`.
   Gate публичного endpoint'а (`EXISTS ... AND deleted_at IS NULL`) корректно держит
   файл доступным, пока жива ≥1 ссылка из любого сообщения.

---

## Архитектура: поток данных

```
Загрузка (eager):
  юзер → скрепка/drag в ChatPanel
    │
    ▼
  VAC @upload-file {file, roomId}
    │
    ▼
  onUploadFile:
    1. filesApi.upload(file) → POST /api/files (существующий, authed)
    2. {id, original_name, mime_type, size_bytes, is_image, url, thumbnail_url}
    3. pendingAttachment[roomId] = attachmentId
    4. (VAC сам покажет превью в поле ввода)
    │
    ▼
  юзер пишет текст (опционально), жмёт Send
    │
    ▼
  VAC @send-message {content, roomId, replyMessage}
    │
    ▼
  onSend:
    1. attachmentId = pendingAttachment[roomId] (если есть)
    2. store.sendMessage(channelId, content, replyToId, attachmentId)
    3. POST /api/chat/channels/{id}/messages {content, reply_to_id, attachment_id}
    4. clear pendingAttachment[roomId]
    │
    ▼
  backend send_message:
    1. _require_staff, rate-limit, _require_channel_access
    2. валидация reply_to_id (существующая) — graceful drop при невалидном
    3. валидация attachment_id (НОВАЯ):
       SELECT 1 FROM files WHERE id=%s AND uploaded_by=%s
       если нет → attachment_id = None (graceful drop)
    4. INSERT messages (channel_id, author_id, content, reply_to_id, attachment_id)
    5. WS fanout → message с attachment meta
    │
    ▼
  toMessage (адаптер): attachment → VAC message.file
    │
    ▼
  VAC рендерит:
    - картинка: <img src="/api/chat-attachments/{id}/thumbnail">
    - документ: иконка по типу + имя + размер + ссылка

Раздача (public, без auth):
  GET /api/chat-attachments/{file_id}
    │
    ▼
  FastAPI handler (без get_current_user):
    1. SELECT f.* FROM files f WHERE f.id = %s
    2. gate: EXISTS(SELECT 1 FROM messages
                    WHERE attachment_id = f.id AND deleted_at IS NULL)
       если не привязан к живому сообщению → 404
    3. StreamingResponse (media_type, Content-Disposition, как /api/files)

  GET /api/chat-attachments/{file_id}/thumbnail
    → аналогично, отдаёт thumbnail_path; 404 для не-картинки
```

---

## Схема БД (миграция 012)

```sql
-- Migration 012: chat message attachments (Подсистема II — интеграция)
-- Idempotent natively: ADD COLUMN IF NOT EXISTS (PG 9.6+), CREATE INDEX IF NOT EXISTS (PG 9.5+).
ALTER TABLE messages ADD COLUMN IF NOT EXISTS attachment_id
    BIGINT NULL REFERENCES files(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_messages_attachment
    ON messages (attachment_id) WHERE attachment_id IS NOT NULL;
```

**Почему так:**
- `BIGINT` — соответствует `files.id` (BIGSERIAL) и `reply_to_id` (тоже BIGINT).
- `ON DELETE SET NULL` — файл удалили → сообщение живёт, как `reply_to_id` и
  `users.avatar_file_id`. Физическое удаление файлов пока не делается (soft only),
  но колонка ведёт себя корректно если когда-нибудь добавят.
- **Partial index** `WHERE attachment_id IS NOT NULL` — большинство сообщений без
  вложений; разреженный индекс дёшев и не раздувает таблицу.
- SQL-блок выше **самодостаточно идемпотентен** через нативные `IF NOT EXISTS`
  (PG 9.6+ для колонки, 9.5+ для индекса) — дешевле `DO $$ ... BEGIN ... END $$`
  и не расходится с прозой. Существующие 009/010/011 используют DO-блоки для
  `CREATE TABLE` (где нет нативного `IF NOT EXISTS`); для `ADD COLUMN` нативная
  форма предпочтительна. Запускать многократно безопасно (повторный `apply_all`
  в lifespan не упадёт).

---

## Backend изменения

### `backend/services/chat_service.py`

**`list_messages`** (lines 194-242) — расширить SELECT и JOIN:

Текущий FROM/JOIN:
```sql
FROM messages m
LEFT JOIN users u ON u.id = m.author_id
LEFT JOIN messages p ON p.id = m.reply_to_id
LEFT JOIN users pu ON pu.id = p.author_id
```

Новый — добавить files:
```sql
LEFT JOIN files f ON f.id = m.attachment_id
```

Добавить в SELECT (после существующих полей, например после `u.avatar_file_id`):
```sql
f.id AS file_id,
f.original_name AS file_name,
f.mime_type AS file_mime,
f.size_bytes AS file_size,
f.is_image AS file_is_image
```

В `_message_row_to_dict` (lines 370-400) — построить `attachment` объект:
```python
attachment = None
if row.get("file_id"):
    attachment = {
        "id": row["file_id"],
        "original_name": row["file_name"],
        "mime_type": row["file_mime"],
        "size_bytes": row["file_size"],
        "is_image": row["file_is_image"],
        "url": f"/api/chat-attachments/{row['file_id']}",
        "thumbnail_url": f"/api/chat-attachments/{row['file_id']}/thumbnail",
    }
# ... и добавить "attachment": attachment в возвращаемый dict
```

> ⚠️ **Канарейка (наследие 07-04, known issue 8):** фикстура `seeded_msgs` в
> `test_chat_messages.py` создаёт `messages` inline CREATE TABLE (lines 36-41) —
> жёстко перечисляет колонки. Новую колонку `attachment_id` **обязательно** добавить
> в эту CREATE TABLE, иначе тесты упадут на `column does not exist`. Аналогично при
> любом будущем расширении SELECT.

**`send_message`** (lines 245-321) — расширить валидацию и INSERT:

В `MessageCreate` (`backend/schemas/chat.py:14-16`) добавить поле:
```python
attachment_id: Optional[int] = None
```

В `send_message`, после валидации `reply_to_id` (lines 263-273), добавить блок
валидации вложения (зеркало логики reply — graceful drop):
```python
attachment_id = data.attachment_id
if attachment_id is not None:
    cur.execute(
        "SELECT 1 FROM files WHERE id = %s AND uploaded_by = %s",
        (attachment_id, current_user["id"]),
    )
    if cur.fetchone() is None:
        # graceful drop — чужой/несуществующий/удалённый файл, текст не теряем
        attachment_id = None
```

В INSERT (lines 275-282) — добавить колонку:
```sql
INSERT INTO messages (channel_id, author_id, content, reply_to_id, attachment_id)
VALUES (%s, %s, %s, %s, %s)
RETURNING id, created_at
```

В возвращаемом dict (lines 306-319) — если `attachment_id` задан, построить `attachment`
объект (аналогично `_message_row_to_dict`). Удобно вынести построение в общий хелпер
`_attachment_dict(file_id, name, mime, size, is_image)`, чтобы не дублировать в двух местах.

**`edit_message`** — НЕ трогать. Редактирование текста не меняет вложение.
(Attachment — атрибут создания сообщения, как reply-parent. Это сознательный YAGNI.)

### `backend/services/file_service.py`

Новая функция — `get_file_by_attachment(file_id: int) -> Tuple[Dict, str]`:
```python
def get_file_by_attachment(file_id: int) -> Tuple[Dict, str]:
    """Gate: file must be attached to a non-deleted message.
    Returns (meta, abs_path). Raise 404 if not found / not attached / missing on disk.
    """
    # SELECT f.* FROM files f WHERE f.id = %s
    # затем gate: EXISTS(SELECT 1 FROM messages WHERE attachment_id = f.id AND deleted_at IS NULL)
    # если нет row или не прошёл gate → raise 404
    # если файла нет на диске → raise 404
    ...
```

Возвращает тот же `meta`-формат, что `get_file` (id, uploaded_by, storage_path,
thumbnail_path, original_name, mime_type, size_bytes, is_image). **Без owner-check** —
gate по attachment-existence заменяет его для публичной раздачи.

Хелпер `_stream_file_response(meta, abs_path)` можно вынести общий (используется
`get_file`, `get_file_by_attachment`, `get_thumbnail_path`), чтобы не дублировать
заголовки/StreamingResponse. Если рефакторинг трогает слишком много — оставить как
есть, новый endpoint пишет свой StreamingResponse inline (scope discipline).

### `backend/routes/files.py`

Два новых endpoint'а — **публичные, без `get_current_user`**:

```python
@router.get("/api/chat-attachments/{file_id}")
def download_attachment(file_id: int):
    """Public. Gate: file must be attached to a non-deleted message."""
    meta, abs_path = get_file_by_attachment(file_id)
    # StreamingResponse — копия GET /api/files/{id}, тот же Content-Disposition (RFC 5987)
    ...

@router.get("/api/chat-attachments/{file_id}/thumbnail")
def download_attachment_thumbnail(file_id: int):
    """Public. 404 if file is not an image / has no thumbnail / not attached."""
    meta, abs_path = get_file_by_attachment(file_id)  # gate
    if not meta.get("thumbnail_path"):
        raise HTTPException(404)
    # StreamingResponse thumbnail, Cache-Control: public, max-age=86400
    ...
```

> ⚠️ **Несоответствие** (trade-off): `/api/avatars/{id}` живёт в `routes/index.py`,
> новые `/api/chat-attachments/...` — в `routes/files.py`. Не переносим аватары
> (scope discipline). Фиксируем inconsistenность; будущий рефактор «все публичные
> media-endpoint'ы в одном месте» — отдельная задача.

### Регистрация

Новый endpoint'ы добавляются в уже зарегистрированный `files_router` — отдельной
регистрации в `routes/index.py` не требуется.

---

## Frontend изменения

### `src/types/chat.ts`

Расширить `ChatMessage`:
```typescript
export interface ChatAttachment {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  is_image: boolean
  url: string                    // "/api/chat-attachments/{id}" — публичный
  thumbnail_url: string | null
}

// в ChatMessage добавить:
attachment?: ChatAttachment | null
```

### `src/composables/useChatAdapter.ts` → `toMessage`

Добавить `file` поле в маппинг (VAC рендерит вложения через `message.file`):
```typescript
file: m.attachment ? {
  name: m.attachment.original_name,
  size: m.attachment.size_bytes,
  type: m.attachment.mime_type,
  url: m.attachment.url,
  ...(m.attachment.is_image ? { previewUrl: m.attachment.thumbnail_url ?? undefined } : {}),
} : undefined,
```

И добавить `file?:` в интерфейс `VACMessage` (lines 15-27).

### `src/components/chat/ChatPanel.vue`

1. `:show-files="false"` (line 154) → `:show-files="true"`
2. Добавить `@upload-file="onUploadFile"` к `<vue-advanced-chat>`. Явно выключить multi-select соответствующим VAC-prop'ом (точное имя — **проверить по исходникам `node_modules/vue-advanced-chat`**, канарейка): дизайн — **одно вложение на сообщение** (VAC `message.file` — single object). Если multi-select выключить нельзя и VAC эмитит несколько файлов — `onUploadFile` берёт `event.detail[0]` и **показывает тост «прикреплён только первый файл»**, остальные игнорируются явно (не молча теряются).
3. Реактивное хранилище pending-вложений (на уровне компонента):
   ```typescript
   const pendingAttachment = reactive<Record<number, number>>({})

   async function onUploadFile(event: { detail: Array<{ file: File; roomId: number }> }) {
     const { file, roomId } = event.detail[0]
     try {
       const { data } = await filesApi.upload(file)
       pendingAttachment[roomId] = data.id
     } catch (e) {
       // toast/error — файл не загрузился, юзер видит это в UI
     }
   }
   ```
4. В `onSend` (lines 87-91) — читать attachmentId и чистить:
   ```typescript
   function onSend(event) {
     const { content, roomId, replyMessage } = event.detail[0]
     const attachmentId = pendingAttachment[Number(roomId)]
     store.sendMessage(Number(roomId), content, replyToIdFrom(replyMessage), attachmentId)
     delete pendingAttachment[Number(roomId)]
   }
   ```
5. Импорт `filesApi` и `StoredFile` типа (если нужен для typing).

### `src/api/chat.ts` + `src/stores/chat.ts`

`sendMessage` в API — расширить payload:
```typescript
sendMessage(channelId: number, data: { content: string; reply_to_id?: number; attachment_id?: number })
```

`store.sendMessage(channelId, content, replyToId?, attachmentId?)` — прокинуть
`attachment_id` в payload. Возвращённое сообщение (с `attachment` meta) уже
аппендится в сторе — extra-логики нет.

> ⚠️ **Канарейка (хэндофф, баги 3+4):** точный contract VAC `@upload-file`
> (`event.detail[0]` shape: `{file, roomId}` или `{file, index, roomId}`?) и
> `@send-message` (приходит ли выбранный файл в payload send-message, или только
> через upload-file?) — **проверить по исходникам `node_modules/vue-advanced-chat`**
> при реализации. Дизайн устойчив к этому: `toMessage` мапит `attachment`→`file`
> независимо от пути загрузки, а `pendingAttachment` — наш собственный стор.
> Если send-message приносит файл в payload — брать оттуда, не дублировать upload.

---

## Безопасность и edge cases

| Случай | Поведение |
|---|---|
| **Публичный enum по id** | Gate: `EXISTS(messages WHERE attachment_id = file.id AND deleted_at IS NULL)`. Только файлы привязанные к живому сообщению. Произвольные приватные файлы (`/api/files/{id}`) через него НЕ доступны. Id перечислимы (BIGSERIAL) — принятый trade-off. |
| **Чужой attachment_id при send** | owner-check (`uploaded_by == user.id`), иначе graceful drop. Текст не теряется. |
| **Soft-delete сообщения** | Gate `deleted_at IS NULL` → вложение недоступно через публичный endpoint. |
| **Hard-delete файла** | `ON DELETE SET NULL` → `attachment_id=NULL` → адаптер рендерит без вложения. Не падаем. |
| **Файл на диске отсутствует** | 404 (как в `get_file`). |
| **Thumbnail для не-картинки** | 404 (как существующий `/api/files/{id}/thumbnail`). |
| **MIME/size/path-traversal (upload-side)** | Переиспользуется `save_upload` без изменений: python-magic по содержимому, двойная проверка MIME AND ext, `secrets.token_hex` в `storage_path` (нет пользовательского ввода в пути), размер чанками. Публичный endpoint раздаёт уже валидированные при загрузке файлы — нового upload-attack-surface нет. |
| **Content-Disposition header injection (response-side)** | Несущий defence — **route-level `urllib.parse.quote()`** на отдаче, ровно как `routes/files.py:49,75`: `Content-Disposition: inline; filename*=UTF-8''{quote(original_name)}`. `quote()` (дефолт `safe='/'`) кодирует `"`, CR, LF, пробел и весь non-ASCII → вырваться за пределы RFC 5987 token нельзя. `sanitize_name` при сохранении — **defense-in-depth**, не первичный контроль. ⚠️ Сознательно НЕ ссылаемся на «покрыто в save_upload»: `save_upload` — путь **загрузки**, а инъекция в заголовке — на **отдаче**, это отдельный слой, и новый endpoint обязан скопировать `quote()`. Новый endpoint без auth → defense-in-depth важнее → регрессионный тест (#16). |
| **Rate limit / scraping (public, no auth)** | Покрывается **глобальным** in-memory лимитером (`rate_limiter.py`, 60 req/min по умолчанию) — тем же, что и `/api/avatars/{id}` (у того нет endpoint-специфичного лимита, сидит на глобальном). ⚠️ **Known limitation:** ключ лимитера — `(IP, exact_path)` включая `file_id` → 60/min **на каждый отдельный id**, а не агрегат по IP → энумерация `/api/chat-attachments/1,2,3,...` каждым id до 60/min не подавляется. Плюс лимитер in-memory → per-worker (×4 воркера на проде, known issue 19). Escape hatch: path-prefix-ключ в `rate_limiter.py` (или signed-URL) — отдельная задача, не этой фазы. Согласовано с тем, как уже работает `/api/avatars/{id}`. |
| **Переиспользование attachment_id** | РАЗРЕШЕНО (см. «Решения» п.5). Один файл → много сообщений. Gate публичного endpoint'а корректно держит файл доступным при ≥1 живой ссылке. |
| **Orphan-файлы (eager без send)** | Накапливаются. Cleanup-job — отдельная задача (known issues); при реализации считать `COUNT` ссылок (см. п.5 «Решения»), не `EXISTS`. В этой фазе не делаем. |
| **Race при быстрой повторной загрузке** | Юзер выбрал второй файл до завершения upload первого → `pendingAttachment[roomId]` перезапишется тем, что зарезолвилось последним (не обязательно вторым); проигравший upload станет orphan молча. Мелочь на масштабе CRM, не блокер. Смягчение (опционально, не обязательно этой фазой): флаг `uploading[roomId]`, игнорировать/тостить второй выбор пока первый в полёте. |
| **Файл удалён после отправки (орфан)** | Сообщение показывает «нет вложения» — `attachment_id` стал NULL, `toMessage` рендерит без `file`. Текст цел. |
| **attachment + reply вместе** | Оба проходят независимую валидацию (reply → lines 263-273, attachment → новый блок). Оба могут быть в одном сообщении. |
| **VAC web-component quirks** | Object-props — JSON.stringify (наследие known issue 1). Event-payload'ы — читать из исходников VAC, не угадывать (known issue 3). |

---

## Тестирование (TDD)

### Backend (pytest)

Расширить `backend/tests/test_chat_messages.py` (обновить фикстуру `seeded_msgs` под
новую колонку `attachment_id`) и `backend/tests/test_files.py` (новый публичный endpoint):

| # | Тест | Что проверяет |
|---|---|---|
| 1 | `test_list_messages_includes_attachment` | сообщение с attachment_id → payload содержит `attachment` с meta (id, name, mime, size, is_image, url, thumbnail_url) |
| 2 | `test_list_messages_attachment_null_when_no_file` | сообщение без вложения → `attachment: None` |
| 3 | `test_send_message_with_valid_attachment` | send с валидным своим attachment_id → сообщение возвращается с `attachment` meta |
| 4 | `test_send_message_with_nonexistent_attachment_graceful_drop` | send с `attachment_id=999999` → attachment обнулён, текст сохранён, 200 (не 4xx) |
| 5 | `test_send_message_with_foreign_attachment_graceful_drop` | send с чужим attachment_id (uploaded_by != current) → graceful drop |
| 6 | `test_send_message_with_attachment_and_reply` | оба поля заданы, оба валидны → оба в payload |
| 7 | `test_public_attachment_endpoint_200_for_attached` | `GET /api/chat-attachments/{id}` без auth → 200, верный Content-Type |
| 8 | `test_public_attachment_endpoint_404_for_unattached` | файл существует, но не привязан к сообщению → 404 (gate) |
| 9 | `test_public_attachment_endpoint_404_for_deleted_message` | файл привязан к soft-deleted сообщению → 404 |
| 10 | `test_public_attachment_thumbnail_200_for_image` | `/thumbnail` для картинки → 200 image/jpeg |
| 11 | `test_public_attachment_thumbnail_404_for_non_image` | `/thumbnail` для PDF → 404 |
| 12 | `test_attachment_fk_set_null_on_file_delete` | DELETE file → message.attachment_id становится NULL |
| 16 | `test_public_attachment_content_disposition_safe` | upload файла с именем, содержащим `"`, CR (`\r`), LF (`\n`) → `GET /api/chat-attachments/{id}` → заголовок `Content-Disposition` не содержит сырых `"`/CR/LF (всё percent-закодировано через `quote()`). Регрессия на response-side header injection (точка безопасности, поднятая на ревью спеки). |

### Frontend (vitest)

| # | Тест | Что проверяет |
|---|---|---|
| 13 | `toMessage maps attachment to VAC file (image)` | attachment с `is_image=true` → `file.previewUrl` задан |
| 14 | `toMessage maps attachment to VAC file (document)` | attachment с `is_image=false` → `file` без `previewUrl`, с url/name/size/type |
| 15 | `ChatPanel onUploadFile calls filesApi.upload and stores pending` | mount → emit upload-file → assert filesApi.upload called + pendingAttachment[roomId] set |

**Ожидаемый счёт:** 180 → ~191 backend (+11-13, включая regression-тест на Content-Disposition), 15 → 17-18 frontend (+2-3).

---

## Деплой-задачи

1. **Backup БД** перед миграцией 012 (`pg_dump hhb_b2b | gzip > /root/crmks_backup_$(date +%Y%m%d_%H%M%S).sql.gz`).
2. **Миграция 012** — auto через `apply_all` в lifespan при рестарте.
3. **Новые deps — НЕТ.** Pillow/python-magic/libmagic уже стоят (родительская спека).
4. **nginx — НЕ ТРОГАЕМ.** `client_max_body_size 100m` уже стоит (родительская спека).
5. **MEDIA_ROOT — НЕ ТРОГАЕМ.** Права `crmks:crmks` уже настроены.
6. **Перезапуск:** `systemctl restart crmks-api`, подождать ~5s.
7. **Smoke:**
   - `POST /api/files` (с auth, PDF) → 200, получили `{id, ...}`.
   - `POST /api/chat/channels/{id}/messages` с `attachment_id` → 200, payload с `attachment`.
   - `GET /api/chat-attachments/{id}` **без auth** → 200, верный Content-Type.
   - `GET /api/chat-attachments/999999` без auth → 404.
   - Логи: `tail -50 /var/log/crmks/api.log`.

---

## Порядок реализации (для плана)

1. **Backend schema + service:** миграция 012 + `send_message` валидация/INSERT +
   `list_messages` JOIN + `_message_row_to_dict` attachment-поле + tests 1-6.
2. **Backend public endpoint:** `get_file_by_attachment` + `GET /api/chat-attachments/{id}`
   + `/thumbnail` + tests 7-12.
3. **Frontend types + adapter:** `ChatAttachment` тип + `ChatMessage.attachment` +
   `toMessage` file-маппинг + tests 13-14.
4. **Frontend ChatPanel + store:** `:show-files=true`, `@upload-file`, `pendingAttachment`,
   `store.sendMessage` с attachment_id + test 15.
5. **Деплой:** backup + рестарт + smoke.

Каждый этап — независимо тестируемый. Backend (1-2) можно деплоить без frontend и
проверять curl'ом. Frontend (3-4) — без backend, против mock'ов.

---

## Риски и компромиссы

- **Публичный endpoint enum по id** — любой со знанием id скачает attachment-файл.
  Gate ограничивает до «привязанные к живому сообщению», но не делает id
  неперечислимыми. Для CRM с внутренними staff-юзерами приемлемо (аналог аватарок).
  Если später понадобится stricter — signed-URL'ы (короткоживущие токены) или
  continuation-через `/api/chat/channels/{id}/messages/{mid}/attachment` (authed).
- **Orphan-файлы от eager upload** — копятся, если юзер загрузил, но не отправил.
  Cleanup-job (удалять files без messages-ссылки старше N дней) — отдельная задача.
  На масштабе CRM (десятки staff) незаметно.
- **Несогласованность публичных endpoint'ов** — `/api/avatars/{id}` в index.py,
  `/api/chat-attachments/{id}` в files.py. Косметика, не блокер.
- **VAC contract uncertainty** — точный shape `@upload-file` event и наличие файла
  в `@send-message` payload надо сверить с исходниками VAC. Дизайн устойчив
  (pendingAttachment — наш стор, toMessage не зависит от пути), но реализация
  должна читать VAC-исходники, не угадывать (канарейка из хэндоффа).
- **Single attachment per message** — VAC `message.file` = single object. Множественные
  вложения потребуют либо array-field (VAC может не поддерживать), либо нескольких
  сообщений. Выяснится при использовании, сейчас YAGNI.

---

*Спека написана с любовью. 💕 Канарейка на посту — паттерны публичных endpoint'ов и
VAC-граблей отработаны на аватарках (07-05), owner-check/graceful-drop — на reply (07-04).
Базовый файловый сервис переиспользуется без изменений, YAGNI соблюдён.*
