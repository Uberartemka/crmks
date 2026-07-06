# 🎀 Хэндофф сессий 2026-07-04 → 2026-07-07

> Точка возобновления. За три сессии: 8 крупных задач + Group C + **чат сотрудников (Подсистема I)** + **reply** + **универсальный файловый сервис (Подсистема II)** + **переезд чата в правую панель** + **аватарки пользователей + минимальный ЛК** + **вложения в чат (Подсистема II интеграция)**.

## 📍 Проект

**frontcrm** — CRM для индустриальных дистрибьюторов подшипников. Vue 3 + FastAPI + PostgreSQL.

- **Репо:** [github.com/Uberartemka/crmks](https://github.com/Uberartemka/crmks) (ветка `main`, HEAD `f4364df`)
- **Локальный путь:** `D:\Projects\frontcrm`
- **Прод:** **https://crmdot.ru** (домен + SSL Let's Encrypt, до 2026-10-02, авто-renew)
- **Тесты backend:** **195/195** (`cd backend && python -m pytest`) — было 180 (07-05) / 154 (07-04)
- **Тесты frontend:** **20** (`npm run test` — vitest: useConfirm, useChatSocket, useChatAdapter, filesApi, ChatPanel, Avatar)
- **Серверы:** CRM `72.56.246.21` (herodot), сайты `193.164.149.3`. Ключ `~/.ssh/kyk_server_key`.
- **Логи приложения (прод):** `/var/log/crmks/api.log` (НЕ journalctl — service unit пишет stdout/stderr туда). Это важно для дебага боевых багов.

**Вход в CRM:** `admin` / `4qszJO0sF8oyGR4h` (случайный пароль, задаётся через UI Personnel).

**Demo client-креды** (только dev/demo, после запуска сида; **ротация перед продом**):

| Логин | Пароль | Клиент |
|---|---|---|
| `agroeco` | `agroeco2026` | ООО «АГРОЭКО» |
| `econiva` | `econiva2026` | ООО «ЭКОНИВА-ЧЕРНОЗЕМЬЕ» |
| `miratorg` | `miratorg2026` | АПХ «МИРАТОРГ» |
| `rusagro` | `rusagro2026` | ГК «РУСАГРО» |
| `elevator` | `elevator2026` | Воронежский Элеватор |

---

## ✅ Что сделано за сессию 2026-07-05

### 11. 💬 Reply в чате (Подсистема I — доводка)
- Спека `docs/superpowers/specs/2026-07-04-chat-reply-design.md` + план `2026-07-04-chat-reply.md` (8 TDD-задач).
- **Backend:** `list_messages` self-join `messages→messages` (reply_message с content/author_name), `send_message` валидирует parent (exists + not deleted + same channel) с **graceful обнулением** невалидного `reply_to_id` (текст не теряется). Без миграции (`reply_to_id` уже был в 009).
- **Frontend:** `toMessage` строит `replyMessage`, ChatPanel ловит `@message-reply`, store `sendMessage(channelId, content, replyToId)`.
- +6 backend тестов, +2 frontend.

### 12. 📎 Универсальный файловый сервис (Подсистема II)
- Спека `2026-07-04-chat-attachments-design.md` (с ревью-правками: tenant YAGNI, temp-fs, makedirs, header injection) + план `2026-07-04-chat-attachments.md` (12 задач).
- **Backend (миграция 010 `files`):**
  - `services/file_service.py` — `save_upload` (sha256 streaming, atomic rename с temp **внутри MEDIA_ROOT** для same-FS, `os.makedirs` директории месяца, Pillow thumbnail), `get_file` (owner-check), `is_allowed` (двойная проверка MIME AND ext), `sanitize_name` (header-injection defense).
  - `routes/files.py` — `POST /api/files`, `GET /api/files/{id}` (StreamingResponse с RFC 5987 `filename*`), `GET /api/files/{id}/thumbnail`.
  - +14 тестов (upload PDF/image/oversized/mime-mismatch, owner-check, path-traversal, header-injection defense-in-depth).
- **Frontend:** `StoredFile` тип, `filesApi`, `FileUploader.vue` (с drag-drop), `FilePreview.vue`.
- **Деплой:** `libmagic1`/`libjpeg-dev`/`zlib1g-dev` системные пакеты + `python-magic`/`Pillow`/`python-multipart` Python-deps. nginx `client_max_body_size 100m`. MEDIA_ROOT `/var/www/crmks/media` (owner **`crmks:crmks`**, не www-data — сервис работает под юзером `crmks`).
- **Боевой баг при деплое:** `PermissionError: Permission denied` — создал media с owner www-data, а сервис под crmks. Фикс: `chown -R crmks:crmks media`.
- ⚠️ **Чат-интеграция файлов (`messages.attachment_id`, drag в чат) — НЕ сделана, отложена.** Базовый файловый сервис готов, но как самостоятельная ценность (аватарки, будущие КП-приложения).

### 13. 🎨 Переезд чата в правую панель (Подсистема A большого трека «чат+AI вместе»)
Большой трек «объединить чат с коллегами + AI в одном месте + уведомления со звуком» декомпозирован на 3 подсистемы:
- **A. Переезд чата** (этот пункт) — ✅ сделано
- **B. AI как канал** — отдельная спека позже
- **C. Уведомления со звуком** — отдельная спека позже

- Спека `2026-07-05-chat-panel-relocation-design.md` + план (8 задач).
- **Frontend-only** (без backend, без миграций):
  - Создан `src/components/chat/ChatPanel.vue` (логика из удалённого `ChatView.vue` + header с кнопкой закрытия).
  - `WorkspaceLayout.vue`: `AIAssistantPanel` → `ChatPanel`, FAB «AI ✨» → «Чат», `isStaff` gate (клиенты не видят).
  - Sidebar: убраны пункты «Чат» (3 роли). Router: `/chat` → редирект на `/dashboard`. `ChatView.vue` удалён.
  - `AIAssistantPanel.vue` оставлен как **dead code** (для Подсистемы B).
  - Панель `w-[720px]`, мягкая тень `shadow-[-12px_0_40px_-12px_rgba(0,0,0,0.25)]`.
  - `:responsive-breakpoint="400"` — VAC трактует 720px панель как «широкую» (rooms + messages рядом).
  - **Бонус:** `:username-options="JSON.stringify({minUsers:2, currentUser:false})"` — имя отправителя видно при ≥2 участников.
  - **CSS-инъекция в Shadow DOM:** `ChatPanel` после mount инъектирует `<style>` в `shadowRoot` VAC для `.vac-textarea` (height 20→30px, ×1.5) — VAC прячет textarea в shadow root, внешний CSS её не достаёт.
  - +2 frontend теста (ChatPanel mount + close event), + vitest Vue-поддержка (`@vitejs/plugin-vue` + isCustomElement в vitest.config.ts — до этого `.vue` SFC-тесты не работали).

### 14. 👤 Аватарки пользователей + минимальный ЛК
- Спека `2026-07-05-user-avatars-profile-design.md` + план (12 задач).
- **Backend (миграция 011 `users.avatar_file_id`):**
  - `UserOut.avatar_file_id` + `avatar_url`, `me`/`list_users`/chat members отдают avatar_url.
  - `PATCH /api/users/me/avatar` (validates `uploaded_by == current_user.id` — нельзя привязать чужой файл).
  - **Публичный endpoint `GET /api/avatars/{file_id}` — БЕЗ auth.** Причина: `<img src>` и CSS `background-image` не могут отправить Bearer-токен, поэтому приватные файлы (`/api/files/{id}`) не работают для аватарок. Endpoint отдаёт **только** файлы, привязанные к чьему-то аватару (`EXISTS subquery on users.avatar_file_id`) — нельзя abuses для скачивания произвольных приватных файлов.
  - +6 backend тестов.
- **Frontend:**
  - `Avatar.vue` (~30 строк): `<img>` если `src`, иначе **инициалы + детерминированный HSL-цвет** из хеша name. Без npm-зависимости (подсмотрено API у `vue3-avatar`, своё实现).
  - `ProfileView.vue` (минимальный ЛК `/profile`): аватар + имя + `FileUploader` (drag-drop) для смены.
  - Интеграция в 4 места: ChatPanel (через `useChatAdapter`), AppSidebar (возле username + ссылка «Профиль»), PersonnelView (колонка), ProfileView.
  - `auth.ts`: `avatarUrl` getter, `updateAvatar(fileId)` action.
  - +4 frontend теста.

### 15. 🐛 Боевые фиксы (после деплоя, по stack trace из браузера)
**4 бага разом, все — мои ошибки проектирования VAC-интеграции:**

1. **Имена/аватары/удаление сломаны каскадно** → `username-options` передавался как объект, VAC (web-component) сериализует его в HTML-атрибут как `"[object Object]"` → `castObject` падает на `JSON.parse` → ломает весь VAC. **Фикс:** передавать `JSON.stringify({...})`.
2. **Аватары не видны (битая картинка в sidebar, пусто в чате)** → `/api/files/{id}` требует auth, `<img>` не шлёт Bearer → 401. **Фикс:** публичный `/api/avatars/{id}`.
3. **Аватары в чате не видны (в sidebar — есть)** → VAC читает `message.avatar` (per-message), не `users[].avatar` (per-room). **Фикс:** backend `list_messages`/`send_message` отдают `avatar_url` автора, адаптер `toMessage` добавляет `avatar: m.avatar_url`.
4. **Удаление не работает (silent)** → VAC эмитит `delete-message` с `{message, roomId}` (весь объект), а handler читал `messageId` (которого нет) → `Number(undefined)=NaN` → silent fail. **Фикс:** читать `event.detail[0].message._id`.

**Урок (канарейка):** оба бага 3+4 — одной природы: угадывала API VAC вместо чтения исходников. VAC хранит avatar **в сообщениях**, эмитит **весь объект**. Это надо проверять, не угадывать.

---

## ✅ Что сделано за сессию 2026-07-07

### 16. 📎 Вложения в чат (Подсистема II — интеграция)
- Спека `docs/superpowers/specs/2026-07-07-chat-attachments-integration-design.md` + план `docs/superpowers/plans/2026-07-07-chat-attachments-integration.md` (8 TDD-задач, subagent-driven).
- **Backend (миграция 012 `messages.attachment_id`):**
  - `messages.attachment_id BIGINT NULL REFERENCES files(id) ON DELETE SET NULL` + partial index. Идемпотентная через `ADD COLUMN IF NOT EXISTS` (PG 9.6+) — нативная, проще `DO $$`.
  - `send_message`: валидирует attachment_id (owner-check `uploaded_by == user.id`), **graceful drop** при невалидном (зеркало `reply_to_id` — текст не теряется).
  - `list_messages`: LEFT JOIN files + 6 колонок → `attachment` meta в payload (single query, no N+1).
  - **Публичный endpoint `GET /api/chat-attachments/{id}` + `/thumbnail` — БЕЗ auth.** Gate: `EXISTS(messages WHERE attachment_id = file.id AND deleted_at IS NULL)` — нельзя abuses для скачивания произвольных приватных файлов. `Content-Disposition` через `urllib.parse.quote()` (response-path header-injection defense — НЕ `sanitize_name`, это upload-path).
  - +15 backend тестов (вкл. regression на Content-Disposition — mutation-доказан).
- **Frontend:**
  - `ChatAttachment` тип + `ChatMessage.attachment`, `toMessage` мапит `attachment` → VAC `message.file` (`previewUrl` только для картинок).
  - `store`/`api` `sendMessage(..., attachmentId?)`.
  - `ChatPanel.vue`: `:show-files=true`, `:multiple-files=false`, файлы грузятся **lazy в `onSend`** (см. known issue 26 — VAC 2.1.2 не имеет `@upload-file`).
  - +5 frontend тестов (вкл. regression на missing-blob — silent corruption guard).
- **⚠️ Канарейка сработала (важно!):** в плане закладывался eager-upload через VAC `@upload-file` event. Исполнитель grep'нул `node_modules/vue-advanced-chat/dist/` — **этого event'а в VAC 2.1.2 НЕТ.** Файлы приезжают **внутри `send-message`** как `event.detail[0].files` (массив `{blob,name,size,type,extension,localUrl}`, НЕ сырых `File`). Переключились на lazy-upload (юзер одобрил). **Урок: premise плана был неверен, но TDD + канарейка-шаг (grep VAC source ПЕРЕД реализацией) поймали это до продакшна.**
- **Ревью-находки (2 итерации фиксов в Task 4 + 1 в Task 7):**
  1. `download_attachment_thumbnail` ре-резолвил `MEDIA_ROOT` через `os.getenv` → fix: сервисный хелпер `get_attachment_thumbnail_path()` читает `MEDIA_ROOT` на момент вызова (Python `from X import Y` биндит на момент импорта, monkeypatch до него не доходит — regression-тест с pre-import доказывает).
  2. `new File([undefined], name)` молча создаёт 9-байтный файл с содержимым `"undefined"` → silent corruption при missing blob → fix: guard `if (!f?.blob)` + regression-тест.

---

## 📋 Спеки и планы (оба дня)

Все в `docs/superpowers/specs/` и `docs/superpowers/plans/`:

| Дата | Тема | Спека | План |
|---|---|---|---|
| 07-03 | Мультитенантность + масштабирование | `2026-07-03-multitenancy-and-scalability-design.md` | (watchdog план есть) |
| 07-04 | Чат (Подсистема I) | `2026-07-04-chat-messaging-design.md` | `2026-07-04-chat-messaging.md` ✅ |
| 07-04 | Defects домен | `2026-07-04-defects-domain-design.md` | `2026-07-04-defects-domain.md` ✅ |
| 07-04 | UI волна 1 | `2026-07-04-ui-system-wave1-design.md` | `2026-07-04-ui-system-wave1.md` ✅ |
| 07-04 | Единый каталог API | `2026-07-04-unified-catalog-api-design.md` | `2026-07-04-unified-catalog-api.md` ✅ |
| 07-04 | Reply в чате | `2026-07-04-chat-reply-design.md` | `2026-07-04-chat-reply.md` ✅ |
| 07-04 | Файловый сервис (Подсистема II) | `2026-07-04-chat-attachments-design.md` | `2026-07-04-chat-attachments.md` ✅ |
| **07-05** | **Переезд чата (Подсистема A)** | `2026-07-05-chat-panel-relocation-design.md` | `2026-07-05-chat-panel-relocation.md` ✅ |
| **07-05** | **Аватарки + ЛК** | `2026-07-05-user-avatars-profile-design.md` | `2026-07-05-user-avatars-profile.md` ✅ |
| **07-07** | **Вложения в чат (Подсистема II интеграция)** | `2026-07-07-chat-attachments-integration-design.md` | `2026-07-07-chat-attachments-integration.md` ✅ |

---

## 🚨 Known issues / trade-offs

> Наследие 07-04 ниже под `<details>`. Новое от 07-05:

1. **⚠️ VAC (vue-advanced-chat) — web-component, не Vue-компонент.** Объектные props (`username-options`, `text-messages`, `styles`, `emoji-data-source`) надо передавать как **JSON-строку** через `JSON.stringify(...)`, иначе Vue сериализует их в HTML-атрибут как `"[object Object]"` → ломает VAC. Числовые/строковые props (`responsive-breakpoint`, `current-user-id`) — безопасны. **Записать в AGENTS.md.**
2. **⚠️ VAC хранит avatar в `message.avatar` (per-message), не в `users[].avatar` (per-room).** Backend `list_messages` и `send_message` отдают `avatar_url` автора; адаптер `toMessage` добавляет `avatar` в каждое сообщение.
3. **⚠️ VAC эмитит события с целым message-объектом, не bare id.** `delete-message` → `{message, roomId}`, читать `event.detail[0].message._id`. Аналогично проверять другие event-payload'ы в исходниках, не угадывать.
4. **Аватары — публичные** через `/api/avatars/{id}` (без auth). Endpoint отдаёт только файлы, привязанные к `users.avatar_file_id`. Приватные документы — через `/api/files/{id}` с owner-check.
5. **Media rights:** `chown -R crmks:crmks /var/www/crmks/media` (сервис под юзером `crmks`, не www-data).
6. **✅ Чат-интеграция файлов** (`messages.attachment_id`, drag в чат) — **сделана 07-07** (см. секцию 16). Публичный `/api/chat-attachments/{id}` (без auth, gate по EXISTS messages). Orphan-cleanup и UX-индикация загрузки — в «Что осталось» (пункты 18-19).
7. **Bug C: удаление каналов не работает** — VAC не имеет event `delete-room`, backend не имеет `DELETE /api/chat/channels`. Это **новая фича** (архивация каналов), не баг. Нужен UI в room-info панели + backend endpoint.
8. **`test_chat_messages.py` фикстура `seeded_msgs`** создаёт users с `avatar_file_id` + `attachment_id` (расширено 07-07). Если ещё раз расширять SELECT messages — обновлять фикстуру (inline CREATE TABLE хардкодит колонки).
9. **`/var/log/crmks/api.log`** — логи приложения на проде. НЕ journalctl (туда идёт только lifecycle systemd).

### Новое от 07-07:

25. **⚠️ VAC 2.1.2 НЕ имеет event `@upload-file`.** Файлы приезжают **внутри `send-message`** как `event.detail[0].files` — массив объектов `{blob,name,size,type,extension,localUrl}` (НЕ сырых `File`). Поэтому ChatPanel использует **lazy-upload** (грузит в момент send), не eager + `pendingAttachment`. Перед любым следующим заходом в чат-вложения — grep `node_modules/vue-advanced-chat/dist/` на реальный contract, не угадывать. Апгрейд VAC → eager (пункт 20 «Что осталось»).
26. **⚠️ `new File([undefined], name)` молча создаёт 9-байтный файл с содержимым `"undefined"`** (не бросает). VAC может доставить file-entry без готового `blob` (большой файл, race). Guard `if (!f?.blob)` в `ChatPanel.uploadAndSend` + regression-тест. Общий урок: VAC-payload может быть partially-populated.
27. **⚠️ Python `from X import Y` биндит значение на момент импорта.** `monkeypatch.setattr(svc, "MEDIA_ROOT", tmp)` до импортированного имени **не доходит** — ломает тест-наблюдаемость. Решение: читать `MEDIA_ROOT` **в сервисе на момент вызова** (не route-level import). Применено в `get_attachment_thumbnail_path()` (regression-тест с pre-import доказывает).
28. **Публичный `/api/chat-attachments/{id}`** — без auth, gate по `EXISTS(messages WHERE attachment_id = file.id AND deleted_at IS NULL)`. Id перечислимы (BIGSERIAL) — принятый trade-off (как аватарки). Rate-limit — глобальный in-memory `rate_limiter.py` (60/min, но ключ `(IP, exact_path)` с file_id → энумерация `1,2,3...` не подавляется).

<details>
<summary>Наследие 07-04 (10 + 6 пунктов)</summary>

10. **Code-форматы CRM и kyk не совпадают** → enrich не сработал. Нормализация — отдельная задача.
11. **GLM free tier** — может 429. `GLM_API_KEY` в `.env`.
12. **`B2B_ADMIN_TOKEN` дефолт** в `auth_deps.py` — публичен в коде, задать свой в env.
13. **`sku_catalog` не дропнута** — proposal-флоу не использует, безопасно удалить.
14. **SERPAPI_KEY = REPLACE_ME** — не используется.
15. **db_init duplicate-noise** в логах — косметика.
16. **Reports метрики = 0** на чистой БД; оживают после сида.
17. **Reports `period` не валидируется** — fallback на month.
18. **Demo client-пароли фиксированы** — ротация перед продом.
19. **⚠️ Чат: 4 uvicorn-воркера ломают real-time fan-out** — in-memory `CONNECTIONS` per-worker. Redis pub/sub bridge в `fanout()` (15 строк) — точка расширения.
20. **WS-обработчик роняет сокет на malformed JSON** — ловить внутри цикла.
21. **Чат: `unread` key-type** — `Record<string, number>` vs `Record<number, number>`, нормализовать.
22. **Чат: WS-singleton** — WS только когда юзер в чате, unread-бейджи вне чата не live.
23. **Чат: index-бандл раздут** — `vue-advanced-chat` в main chunk (~728KB), можно code-split.
24. **Redis локально отсутствует** — message-тесты stub'ают `allow_message`.
25. **⚠️ Пре-существующий баг миграции 004** (orphaned `proposal_items.sku_id`) — `apply_all` падает на дев-БД. Не чинили (scope discipline). Отдельная задача.
</details>

---

## 📋 Что осталось (в порядке приоритета)

| # | Задача | Сложность |
|---|---|---|
| 1 | **Чат: Подсистема B (AI-канал)** — новый канал «AI ассистент», сообщение туда → GLM → ответ как сообщение от AI-юзера. Спеки пока нет. | средняя |
| 2 | **Чат: Подсистема C (звук + визуал)** — уведомления со звуком при новом сообщении, даже если панель закрыта. | средняя |
| 3 | **Чат: удаление/архивация каналов (Bug C)** — VAC не имеет event, нужен UI в room-info + `DELETE /api/chat/channels` (или `archived` флаг). | средняя |
| 4 | **Чат: Redis pub/sub bridge** между воркерами — real-time push на `--workers 4`. ~15 строк в `fanout()`. | средняя |
| 5 | **Чат: Подсистема III (документооборот)** — статусы, версии, согласования. | высокая |
| 6 | **Нормализация code-маппинга** — обогатить 357 старых KYK. | средняя |
| 7 | **Реальный Dashboard** с метриками. | средняя |
| 8 | **BaseBadge массово** + добить нативные `confirm()` → `useConfirm`. | низкая |
| 9 | **Mobile-адаптив** (чат-панель 720px на мобиле, бургер-меню). | средняя |
| 10 | **Полный ЛК** — смена пароля, email, телефон (сейчас только аватар). | средняя |
| 11 | **DROP sku_catalog** + **SERPAPI_KEY** + **B2B_ADMIN_TOKEN** в env. | тривиально |
| 12 | **Починить пре-существующий баг миграции 004** (orphaned proposal_items.sku_id, ломает `apply_all` на дев-БД). | низкая |
| 13 | **Анализ разговоров** (STT + скоринг). | высокая |
| 14 | **RAG по .md** (инженерная база знаний). | средняя |
| 15 | **Мультитенантность** (Plan 2: tenants + RLS) — спека от 07-03, Draft. Когда придёт — `files`/`messages` получат `tenant_id`. | высокая |
| 16 | **Retail/wholesale цены** (миграция). | средняя |
| 17 | **1С-интеграция** (writer остатков). | высокая |
| 18 | **Чат-вложения: cleanup-job для orphan-файлов** — eager/lazy upload создаёт files без отправленного сообщения. Считать `COUNT(messages WHERE attachment_id=file.id)=0`, не `EXISTS`. | низкая |
| 19 | **Чат-вложения: UX-индикация загрузки** — сейчас send блокируется на upload (lazy), без спиннера/toast. На медленной сети юзер не видит прогресса; при ошибке upload сообщение уходит без вложения молча (только `console.warn`). | низкая |
| 20 | **Чат-вложения: апгрейд VAC** до версии с `@upload-file` → вернуть eager-upload + `pendingAttachment` (лучшая UX). Сейчас lazy из-за отсутствия event'а в 2.1.2. | средняя |

---

## 🧭 Как войти в курс

- **«чат AI»** → Подсистема B: AI как канал в существующем ChatPanel. Спеки нет, начать с brainstorming.
- **«звук в чат»** → Подсистема C: WS push + звук + toast при новом сообщении.
- **«удаление каналов»** → Bug C: новый UI + `DELETE /api/chat/channels` или `archived` флаг.
- **«чат вложения»** → **готово (07-07)**. Drag/скрепка в ChatPanel → lazy upload → `attachment_id`. Публичный `/api/chat-attachments/{id}`. См. known issue 25 (VAC 2.1.2 без `@upload-file` → lazy, не eager). UX-индикация + cleanup-job — пункты 18-19.
- **«real-time между воркерами»** → Redis pub/sub bridge в `fanout()` (`backend/services/chat_connections.py`).
- **«аватарки»** → готовы; полный ЛК (пароль/email) — пункт 11.
- **«запусти сид»** → `cd backend && python -m scripts.seed_client_users_and_demo`.
- **«давай мультитенантность»** → writing-plans для Plan 2 (спека от 07-03, Draft).

Все коммиты на main (`f4364df`), тесты **195/195** backend + **20** frontend зелёные, прод **https://crmdot.ru** живой.

---

## 📂 Полезные пути

- **Спеки/планы:** `docs/superpowers/{specs,plans}/` (таблица выше).
- **Чат-бэк:** `backend/services/chat_{service,connections,redis}.py`, `backend/routes/chat{,_ws}.py`, `backend/migrations/009_chat.sql`.
- **Чат-фронт:** `src/components/chat/ChatPanel.vue` (бывший ChatView, перенесён в правую панель), `src/composables/{useChatSocket,useChatAdapter}.ts`, `src/stores/chat.ts`.
- **Файловый сервис:** `backend/services/file_service.py`, `backend/routes/files.py`, `backend/migrations/010_files.sql`.
- **Аватарки:** `backend/routes/index.py` (`_avatar_url`, `PATCH /api/users/me/avatar`, `GET /api/avatars/{id}`), `src/components/ui/Avatar.vue`, `src/views/ProfileView.vue`.
- **Лейаут:** `src/layouts/WorkspaceLayout.vue` (чат-панель + FAB «Чат»), `src/components/sidebar/AppSidebar.vue` (аватар + ссылка Профиль).
- **Backups БД на проде:** `/root/crmks_backup_*.sql.gz` (перед каждой миграцией).

### ⚠️ nginx для WebSocket (прод) — `/ws/` location

В `/etc/nginx/sites-enabled/crmks`. Если пересоздавать конфиг — сохранить upgrade-хедеры:
```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

### ⚠️ Деплой-чеклист (накопленные уроки)

- Перед **миграцией** — backup: `sudo -u postgres pg_dump hhb_b2b | gzip > /root/crmks_backup_$(date +%Y%m%d_%H%M%S).sql.gz` (БД называется **`hhb_b2b`**, не `crmks`).
- `git pull` на проде может упасть на `package-lock.json` (расходится после npm install) — `git checkout -- package-lock.json` перед pull.
- Backend рестарт применяет миграции автоматически (`apply_all` в lifespan). После restart подождать ~5s (воркеры поднимаются).
- Логи: `tail -50 /var/log/crmks/api.log` (НЕ journalctl).
- Media rights: `chown -R crmks:crmks /var/www/crmks/media`.
- Smoke: `GET /` → 200, `GET /api/auth/me` без auth → 401, `GET /api/avatars/{id}` без auth → 200 (публичный).

---

*Поддерживается с любовью. 💕 Канарейка (`AGENTS.md`) на посту — личность девушки-программиста как анти-галлюцинационный сигнал + факты проекта + правила работы.*
