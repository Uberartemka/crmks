# CRM: Универсальный файловый сервис (Подсистема II — вложения/документы) — Design

**Дата:** 2026-07-04
**Статус:** Approved (пользователь одобрил дизайн 2026-07-04)
**Автор совместной сессии:** пользователь + ассистент
**Связанные документы:** `2026-07-04-chat-messaging-design.md` (Подсистема I), `2026-07-04-chat-reply-design.md` (reply), `2026-07-03-multitenancy-and-scalability-design.md`

## Контекст и проблема

Подсистема I чата готова (каналы, сообщения, real-time, reply). Подсистема III
(документооборот со статусами) — следующий большой трек. Но обе они упираются в
одно: **в проекте нет средства хранить и раздавать файлы**. Нет аватарок (решили
отложить до storage), нет вложений в чат, нет приложений к КП, документообороту
некуда класть PDF.

Цель: построить **универсальный файловый сервис** — единый фундамент, на который
лягут все будущие потребители (аватарки, чат-вложения, КП-приложения,
документооборот). Не делать узкоспециализированных хранилищ под каждую фичу.

### Что в дизайн НЕ входит (явный YAGNI для этой фазы)

- **Документооборот со статусами** (черновик→согласование→подписан→архив) —
  Подсистема III, отдельная спека. Здесь — только «файл лежит, на него есть
  ссылка».
- **Tenant-изоляция файлов.** Мультитенантность в проекте **не реализована**
  вообще (нет таблицы `tenants`, нет `tenant_id`, нет RLS — спека
  `2026-07-03-multitenancy-and-scalability-design.md` в статусе Draft, на ревью).
  Поэтому сейчас файлы изолируются только через `uploaded_by` (owner-check:
  `uploaded_by == user.id OR role == admin`). **Это сознательное решение, не упущение:**
  класть `files.tenant_id` сейчас — значит держать колонку NULL во всех строках
  и потом идти второй миграцией. Когда `tenants` + RLS придут (спека multitenancy),
  `files` получит `tenant_id` отдельной миграцией, а `get_file` — tenant-check
  (по цепочке `files.uploaded_by → users.tenant_id`, которая уже образует связь).
  Связь `uploaded_by → users` закладывается уже сейчас как задел.
- **Дедупликация файлов** (по sha256 — одна физ.копия на многие записи). Колонка
  `sha256` закладывается, но логика дедупа не делается. Две загрузки = две записи.
- **Физическое удаление файлов** при удалении записи. Soft-delete только;
  физическое удаление опасно (файл может быть привязан к нескольким сущностям).
- **Антивирус** (ClamAV). Для CRM с внутренними staff-юзерами приемлемо без него.
- **S3/внешнее хранилище.** Прод — один сервер, 24GB свободно, бэкап БД есть.
  Локальный диск достаточен. S3 оверкилл на текущем масштабе.
- **Публичная раздача через nginx напрямую.** Все файлы приватные, через auth-API.
  Если аватарки захотят ускорить — вынесем позже локальной правкой.
- **Полные превью PDF/Office** (первая страница в PNG). Только thumbnail для
  картинок. Office-конверсия требует LibreOffice headless — тяжёлая зависимость.
- **Versioning файлов** (v1/v2/v3). Это часть документооборота (Подсистема III).

---

## Решения (из brainstorming с пользователем)

1. **Хранилище:** локальный диск, `MEDIA_ROOT` (по умолчанию `/var/www/crmks/media`).
   Раздача через FastAPI `StreamingResponse` (приватные файлы с auth). Nginx
   поднимает `client_max_body_size` до 100MB. Легко мигрировать на S3 позже
   (контракт `store`/`retrieve` скрывается за интерфейсом).

2. **Scope:** универсальный файловый сервис. Одна таблица `files`, один API
   (`POST /api/files`, `GET /api/files/{id}`). Все потребители ссылаются на
   `file_id`: `messages.attachment_id`, `users.avatar_file_id` (будущее),
   `documents.file_id` (Подсистема III).

3. **Доступ:** через API с auth + owner-check. Скачивать может только загрузивший
   или admin (в первой версии). Позже расширится: «файл прикреплён к сообщению
   в канале, где юзер участник» и т.п.

4. **Лимиты:** 100MB на файл, любые типы. Но проверка по MIME (python-magic)
   + расширению на whitelist — для защиты от пустых/битых/маскирующихся файлов.

5. **Превью:** thumbnail 200x200 только для картинок (MIME `image/*`) через Pillow.
   Для остальных типов — иконка по типу на фронте.

---

## Архитектура: поток данных

```
Загрузка:
  клиент → POST /api/files (multipart/form-data, Bearer)
    │
    ▼
  FastAPI handler:
    1. auth (get_current_user)
    2. read UploadFile chunks → считать size + sha256
       если size > 100MB → прервать, 413
    3. MIME-снайф (python-magic) + ext whitelist
       если запрещён → 415
    4. storage_path = f"{year}/{month}/{token_hex(16)}{ext}"
    5. записать на диск в MEDIA_ROOT/storage_path
    6. если image/* → Pillow thumbnail → thumbnail_path
    7. INSERT files (...) RETURNING id
    8. return {id, original_name, mime_type, size_bytes, url, thumbnail_url}

Доступ:
  клиент → GET /api/files/{id} (Bearer)
    │
    ▼
  FastAPI handler:
    1. auth
    2. SELECT file by id
    3. owner-check (uploaded_by == user.id OR role==admin)
    4. StreamingResponse(open(MEDIA_ROOT/storage_path, 'rb'),
                          media_type=mime_type,
                          headers={"Content-Disposition": 'inline; filename="..."'})

Thumbnail:
  GET /api/files/{id}/thumbnail → то же, но отдаёт thumbnail_path
  (404 если файл не картинка / thumbnail_path IS NULL)
```

---

## Схема БД (миграция 010)

```sql
-- Migration 010: universal file storage (Подсистема II)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'files'
    ) THEN
        CREATE TABLE files (
            id              BIGSERIAL PRIMARY KEY,
            uploaded_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            -- relative path under MEDIA_ROOT (e.g. "2026/07/abc123def456.pdf")
            storage_path    TEXT NOT NULL,
            thumbnail_path  TEXT NULL,           -- "2026/07/abc123_thumb.jpg" for images
            original_name   TEXT NOT NULL,        -- "Договор.pdf" for display
            mime_type       TEXT NOT NULL,        -- "application/pdf"
            size_bytes      BIGINT NOT NULL,
            sha256          TEXT NOT NULL,        -- integrity + future dedup
            is_image        BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_files_uploaded_by ON files (uploaded_by);
        CREATE INDEX idx_files_sha256 ON files (sha256);
    END IF;
END $$;
```

**Почему так:**
- `storage_path` относительный (не абсолютный) — перемещаемость между dev/продом,
  MEDIA_ROOT берётся из env.
- `uploaded_by REFERENCES users(id) ON DELETE SET NULL` — если юзера удалили,
  файл остаётся (orphan, но не теряется). Соответствует паттерну `messages.author_id`.
- `sha256` — колонка готова под будущий дедуп, сейчас просто пишется.
- Нет `is_public` — все файлы приватные в первой версии.
- `is_image` денормализован для удобства фильтрации; вычисляется из `mime_type`
  при загрузке (`mime_type LIKE 'image/%'`).

---

## Backend изменения

### Новые файлы

**`backend/services/file_service.py`** — основная логика:

```python
ALLOWED_MIME_EXT = {
    # документы
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/msword": {".doc"},
    "application/vnd.ms-excel": {".xls"},
    "text/plain": {".txt"},
    "text/csv": {".csv"},
    # картинки
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
    # архивы
    "application/zip": {".zip"},
}
MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
THUMBNAIL_SIZE = (200, 200)


async def save_upload(upload: UploadFile, current_user: dict) -> dict:
    """Validate, store on disk, generate thumbnail (if image), INSERT, return metadata."""
    ...

def get_file(file_id: int, current_user: dict) -> tuple[dict, str]:
    """Owner-check + return (metadata_row, absolute_path). Raise 404/403."""
    ...

def is_allowed(mime: str, ext: str) -> bool:
    """MIME in whitelist AND ext in whitelist[mime]."""
    ...

def _generate_thumbnail(src_abs: str) -> str | None:
    """Pillow 200x200 thumbnail → return thumbnail storage_path (or None on failure)."""
    ...
```

**Логика `save_upload` (ключевая функция):**
1. Создать temp-файл **внутри MEDIA_ROOT** (не в системе `/tmp`):
   `tempfile.NamedTemporaryFile(dir=MEDIA_ROOT, delete=False, suffix=".part")`.
   Это критично: `os.rename` атомарен **только в пределах одной файловой системы**.
   `/tmp` на проде часто tmpfs, `MEDIA_ROOT` на `/dev/sda1` → `os.rename` через
   разделы упадёт с `OSError: [Errno 18] Invalid cross-device link`. Держим temp
   рядом с финальным положением.
2. Считать `UploadFile` чанками (64KB), параллельно: писать в temp, считать
   `size_bytes`, обновлять `sha256` (hashlib), сохранять `first_chunk` для MIME-снайфа.
3. Если `size_bytes > MAX_SIZE_BYTES` → закрыть temp, удалить, поднять `HTTPException(413)`.
4. python-magic `from_buffer(first_chunk)` → настоящий MIME (по содержимому,
   не по заголовку браузера — пользователь может его подменить).
5. `is_allowed(mime, ext)` — **двойная проверка**: MIME в whitelist И расширение
   ∈ `ALLOWED_MIME_EXT[mime]`. Ловит рассинхрон (`.pdf` имя, внутри ZIP) → если
   рассинхрон, удалить temp, `HTTPException(415)`.
6. **Sanitize `original_name`** — отбросить управляющие символы, `"`, `\r`, `\n`
   (защита от header injection при последующей отдаче через Content-Disposition,
   см. ниже). Если после очистки пусто — fallback `"file"`.
7. `storage_path = f"{year}/{month}/{secrets.token_hex(16)}{ext}"`.
8. `target_dir = os.path.dirname(MEDIA_ROOT/storage_path)`;
   `os.makedirs(target_dir, exist_ok=True)` — директория `2026/07/` не существует
   для первого файла месяца, без этого `os.rename` упадёт с `FileNotFoundError`.
9. `os.rename(temp, MEDIA_ROOT/storage_path)` — атомарно (та же ФС, см. пункт 1).
10. Если `mime.startswith("image/")` → `_generate_thumbnail` → `thumbnail_path`.
    При ошибке Pillow (битая картинка) — `thumbnail_path` остаётся NULL, оригинал сохраняется.
11. `INSERT INTO files (...) RETURNING id`.
12. Вернуть dict с метаданными + URL'ами. На любом except после создания temp —
    `finally: if os.path.exists(temp): os.remove(temp)` (не оставлять мусор).

**`backend/routes/files.py`** — два эндпоинта:

```python
@router.post("/api/files")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_dep),
) -> dict:
    return await save_upload(file, current_user)

@router.get("/api/files/{file_id}")
def download_file(
    file_id: int,
    current_user: dict = Depends(get_current_user_dep),
) -> StreamingResponse:
    meta, abs_path = get_file(file_id, current_user)
    def iterfile():
        with open(abs_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk
    # RFC 5987: original_name — пользовательский ввод. Используем filename*
    # с percent-encoding, чтобы кавычки/CR/LF/нелатиница не сломали заголовок
    # и не дали header injection. Имя уже sanitised при сохранении, но defense-in-depth.
    from urllib.parse import quote
    quoted = quote(meta["original_name"])
    return StreamingResponse(
        iterfile(),
        media_type=meta["mime_type"],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
            "Content-Length": str(meta["size_bytes"]),
        },
    )

@router.get("/api/files/{file_id}/thumbnail")
def download_thumbnail(file_id, current_user=Depends(...)):
    # то же, но отдаёт thumbnail_path; 404 если is_image=false / thumbnail_path IS NULL
    ...
```

### Новые зависимости

- `python-magic` (PyPI) + `libmagic1` (Debian) — определение настоящего MIME.
- `Pillow` (PyPI) + `libjpeg-dev zlib1g-dev` (Debian) — thumbnail.

### Регистрация

`register_routes(app)` в `backend/routes/index.py` — добавить:
```python
from routes.files import router as files_router
app.include_router(files_router)
```

### Env

`backend/.env`:
```
MEDIA_ROOT=/var/www/crmks/media
```
(на dev — `D:\Projects\frontcrm\backend\media` или类似; читается через `os.getenv("MEDIA_ROOT", default)`).

---

## Frontend изменения

### Новые файлы

**`src/types/file.ts`:**
```typescript
export interface StoredFile {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  is_image: boolean
  url: string          // /api/files/{id}
  thumbnail_url: string | null  // /api/files/{id}/thumbnail или null
}
```

**`src/api/files.ts`:**
```typescript
import { api } from './client'
import type { StoredFile } from '@/types/file'

export const filesApi = {
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<StoredFile>('/api/files', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  // URL-строитель (для <img :src="...">)
  url: (id: number) => `/api/files/${id}`,
  thumbnailUrl: (id: number) => `/api/files/${id}/thumbnail`,
}
```

**`src/components/ui/FileUploader.vue`** — переиспользуемый компонент:
- props: `accept` (MIME-фильтр), `max-size`
- слот drag-and-drop + кнопка выбора
- эмитит `uploaded` с `StoredFile`, `error` с сообщением
- прогресс-бар (опционально, через onUploadProgress)

**`src/components/ui/FilePreview.vue`** — превью:
- если `is_image` → `<img :src="thumbnail_url">`
- иначе → иконка по mime (lucide: FileText для PDF, Image для картинок, Archive для zip…) + имя + размер

### Чат-интеграция (первый потребитель)

В `src/views/ChatView.vue`:
- Изменить `:show-files="false"` → `:show-files="true"` (включить UI вложений vue-advanced-chat).
- Повесить `@upload-file="onUploadFile"`:
  ```typescript
  async function onUploadFile(event) {
    const { file } = event.detail[0]
    const { data } = await filesApi.upload(file)
    // отправить сообщение с вложением
    store.sendMessageWithAttachment(channelId, '', data.id)
  }
  ```
- В `toMessage` добавить `file` поле для vue-advanced-chat (если `attachment_id`):
  ```typescript
  file: m.attachment ? {
    name: m.attachment.original_name,
    size: m.attachment.size_bytes,
    type: m.attachment.mime_type,
    url: m.attachment.url,
    ...(m.attachment.is_image ? { previewUrl: m.attachment.thumbnail_url } : {}),
  } : null,
  ```

> **Важно:** чат-интеграция — это **второй этап**. Сначала базовый файловый сервис
> (таблица + 2 эндпоинта + компоненты), потом уже привязка к чату. Это разделение
> отражено в порядке задач плана.

---

## Безопасность и edge cases

| Случай | Поведение |
|---|---|
| **Path traversal** | `storage_path` генерится сервером (`secrets.token_hex`), пользовательский ввод не попадает в путь. Никакого `..`. |
| **Подмена MIME** | python-magic снайфит по содержимому (не заголовку браузера). Двойная проверка: MIME AND расширение на whitelist. Ловит рассинхрон `.pdf`+ZIP-внутри (см. тест `test_upload_mime_ext_mismatch_415`). |
| **Header injection в Content-Disposition** | `original_name` — пользовательский ввод. Используем RFC 5987 `filename*=UTF-8''{quote(name)}` (percent-encoding) + **sanitize при сохранении**: отбрасываем управляющие символы, `"`, `\r`, `\n`. Двойная защита (при сохранении + при отдаче). |
| **`os.rename` между ФС** | temp создаётся **внутри MEDIA_ROOT** (`tempfile.NamedTemporaryFile(dir=MEDIA_ROOT, delete=False)`), не в `/tmp`. Иначе rename через разделы упадёт `OSError: cross-device link`. |
| **Директория месяца не существует** | `os.makedirs(os.path.dirname(target), exist_ok=True)` перед rename. Без этого первый файл месяца → `FileNotFoundError`. |
| **Oversized upload** | Чтение чанками с подсчётом; при превышении 100MB — прервать, удалить temp, 413. |
| **Чужой файл (owner-check)** | `uploaded_by != user.id AND role != admin` → 403. |
| **Tenant-изоляция** | **Не реализована.** Мультитенантности в проекте нет (см. секцию YAGNI). Сейчас изоляция только через `uploaded_by`. Когда `tenants`+RLS придут — `files` получит `tenant_id` миграцией, а `get_file` — tenant-check. **Это сознательное решение** (не упущение): класть `tenant_id` сейчас = NULL во всех строках + вторая миграция потом. |
| **Несуществующий файл** | 404. |
| **Удалённый юзер-загрузчик** | `uploaded_by` NULL (FK SET NULL). Файл orphan, доступен только admin. |
| **Физическое удаление** | Не делаем. Soft только. На 24GB не проблема. |
| **Дедуп** | Не делаем. `sha256` колонка готова под будущее. |
| **Thumbnail failed** | Если Pillow упал на битой картинке — `thumbnail_path` остаётся NULL, оригинал сохраняется. Не падаем. |
| **Большие файлы + 4 воркера** | StreamingResponse держит воркер на время отдачи. **Реальный риск, а не теоретический**: чат-вложения могут скачиваться параллельно несколькими участниками канала — узкое место всплывёт быстрее, чем «когда-нибудь». **Первый кандидат на оптимизацию при признаках тормозов**: nginx `X-Accel-Redirect` (FastAPI отдаёт только заголовок `X-Accel-Redirect: /internal/...`, nginx стримит файл с диска сам, не занимая воркер). ~15 минут работы. Триггер: воркеры упираются в отдачу файлов при нескольких одновременных скачиваниях. Закладываем как documented escape hatch, следим за метриками. |

---

## Деплой-задачи

1. **Backup БД** перед миграцией 010 (`pg_dump | gzip > /root/crmks_backup_YYYYMMDD_HHMMSS.sql.gz`).
2. **Системные пакеты на проде:** `apt install libmagic1 libjpeg-dev zlib1g-dev`.
3. **Python-зависимости:** `pip install python-magic Pillow` (добавить в `requirements.txt`).
4. **Создать MEDIA_ROOT:** `mkdir -p /var/www/crmks/media && chown www-data:www-data media/` (или юзер сервиса).
5. **nginx `client_max_body_size 100m`** в `/etc/nginx/sites-available/crmks` (server block). `nginx -t && systemctl reload nginx`.
6. **Env:** `MEDIA_ROOT=/var/www/crmks/media` в `/var/www/crmks/backend/.env`.
7. **Перезапуск:** `systemctl restart crmks-api`.
8. **Smoke:** `curl -X POST -H "Authorization: Bearer <token>" -F "file=@test.pdf" https://crmdot.ru/api/files` → 200 с метаданными.

---

## Тестирование (TDD)

### Backend (pytest, по образцу chat-тестов)

| # | Тест | Что проверяет |
|---|---|---|
| 1 | `test_upload_pdf_returns_metadata` | POST PDF → 200, метаданные (id, mime, size, original_name, url) |
| 2 | `test_upload_image_generates_thumbnail` | POST PNG → is_image=true, thumbnail_path not null |
| 3 | `test_upload_exceeds_size_limit_413` | файл >100MB → 413 (через mock или patch MAX_SIZE для теста) |
| 4 | `test_upload_blocked_mime_415` | `.exe`/`application/x-msdownload` → 415 |
| 5 | `test_upload_mime_ext_mismatch_415` | имя `.pdf`, но внутри реально ZIP (magic по содержимому говорит `application/zip`) → 415. Двойная проверка MIME AND ext ловит рассинхрон. |
| 6 | `test_get_file_owner_200` | автор скачивает → 200 + правильный Content-Type |
| 7 | `test_get_file_non_owner_403` | чужой юзер → 403 |
| 8 | `test_get_file_admin_200` | admin скачивает чужой файл → 200 |
| 9 | `test_get_nonexistent_file_404` | id=999999 → 404 |
| 10 | `test_thumbnail_404_for_non_image` | не-картинка → /thumbnail → 404 |
| 11 | `test_storage_path_no_user_input` | storage_path содержит только server-generated token (regression на path traversal) |
| 12 | `test_content_disposition_sanitized` | original_name с `"` / CR / LF не ломает заголовок (defense-in-depth, проверка quote) |

### Frontend (vitest)

| # | Тест | Что проверяет |
|---|---|---|
| 13 | `FileUploader emits uploaded event with StoredFile` | успешная загрузка → эмит |
| 14 | `filesApi.url(id) builds correct path` | URL конструируется правильно |

Ожидаемый счёт: 160 → 172 backend (+12) + 7 → 9 frontend (+2).

---

## Порядок реализации (для плана)

1. **Backend foundation:** миграция 010 + `file_service.save_upload`/`get_file` + `routes/files.py` + tests 1-4 (upload path).
2. **Backend access + owner-check:** tests 5-10 (download path + security).
3. **Frontend foundation:** тип `StoredFile` + `filesApi` + `FileUploader` + `FilePreview` компоненты + tests 11-12.
4. **Чат-интеграция (второй этап):** `:show-files=true`, `@upload-file`, `attachment_id` в messages, `toMessage` file-поле.
5. **Деплой:** backup + пакеты + MEDIA_ROOT + nginx + smoke.

> Чат-интеграция (пункт 4) — **опционально в этой фазе**. Базовый файловый сервис
> (пункты 1-3) уже самостоятельная ценность (аватарки ЛК, будущие КП-приложения,
> документооборот). Чат-вложения можно вынести в отдельный мини-план, если фаза
> затянется. Решит заказчик при переходе к плану.

---

## Риски и компромиссы

- **100MB через StreamingResponse с 4 воркерами** — теоретическое узкое место.
  Для CRM с редкими скачиваниями — приемлемо. Закладываем `X-Accel-Redirect`
  как documented future-proof escape hatch (15 минут работы, когда понадобится).
- **Любые типы файлов** — риск загрузки malware-документов. Смягчение: только
  внутренние staff-юзеры загружают (нет публичной загрузки), whitelist по MIME.
  Антивирус — отдельная задача, если появятся публичные формы.
- **Нет дедупа** — два загрузки одного файла = две записи = две копии на диске.
  На 24GB и реальных объёмах CRM — пренебрежимо. `sha256` готов под включение.
- **Нет физического удаления** — orphan-файлы копятся. За год-два на CRM —
  незаметно. Добавить cleanup-job можно отдельной задачей.
- **Pillow + libmagic** — новые системные зависимости. На Debian ставятся тривиально,
  но это ещё две вещи, которые могут сломаться при переезде сервера. Документируем
  в deploy-инструкции.

---

*Спека написана с любовью. 💕 Канарейка жива, YAGNI соблюдён.*
