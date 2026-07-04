# CRM: Чат и взаимодействие сотрудников — Подсистема I (фундамент real-time)

**Дата:** 2026-07-04
**Статус:** Draft (на ревью у пользователя)
**Автор совместной сессии:** пользователь + ассистент

## Контекст и проблема

`frontcrm` вырос в систему с ролями (admin/manager/employee/client), 1213 SKU,
КП, заказами, дефектами и отчётами — но у сотрудников **нет средства
коммуникации между собой**. Задачи создаются и назначаются, заметки приватные,
а общего пространства «обсудить и согласовать» не существует.

Цель верхнего уровня, поставленная пользователем: **«полностью автономный
документооборот и взаимодействие между сотрудниками»** — общий чат для всех,
каналы по отделам и темам, плюс движение документов.

### Декомпозиция (важно)

Запрос «чат + документооборот» — это не одна фича, а **три связанные подсистемы**.
Пытаться реализовать их в одном плане — верный путь к хаосу. Проект декомпозирован:

| # | Подсистема | Зависимости | Сложность | Спека |
|---|---|---|---|---|
| **I** | **Фундамент чата**: real-time транспорт, каналы (общий/отдел/тема), сообщения, участники, unread | auth + Redis | средняя | **этот документ** |
| **II** | **Вложения и файлы**: загрузка, хранение, раздача, привязка к сообщению/каналу | построен на I | средняя | отдельный документ |
| **III** | **Документооборот**: карточки документов со статусами (черновик→согласование→подписан→архив), версии, согласования, привязка к клиенту/КП/заказу | построен на I + II | высокая | отдельный документ |

Порядок реализации: **I → II → III**. Документооборот «через чат» невозможен
без самого чата. Эта спека описывает **только Подсистему I**.

### Что в дизайн НЕ входит (явный YAGNI для Подсистемы I)

- Вложения/файлы → Подсистема II.
- Документы со статусами/согласованиями/версиями → Подсистема III.
- Редактирование сообщений с версионированием (тут — только последняя версия).
- Полнотекстовый поиск по истории (отдельная фича позже).
- Упоминания `@user` / `@channel` / `@here` (позже, если потребуется).
- Redis pub/sub **между воркерами** — закладываем «точку расширения», реализуем
  при переходе на `web:N` из спеки мультитенантности (пока 1 uvicorn-воркер).
- Клиентская коммуникация (client↔manager как тикеты) — отдельный цикл.
- Мобильные push-уведомления (APNs/FCM).

---

## Принцип архитектуры: «запись через REST, доставка через WebSocket»

Устоявшийся паттерн (Slack, Discord, Mattermost): отправка сообщения идёт
обычным HTTP-запросом, который сохраняет в БД и фан-аутит подписчикам через
WebSocket. WebSocket остаётся тонким каналом «только push».

```
 Браузер (staff)                          FastAPI (uvicorn, 1 воркер)
      │                                        │
      │  1. POST /api/chat/ws-ticket           │  in-memory registry:
      │  (Bearer) ───────────────────────────► │   {user_id: set(WebSocket)}
      │  ◄─────────── {ticket} (Redis, 30s)    │
      │                                        │
      │  2. WS /ws/chat?ticket=...             │  fan-out при новом сообщении:
      │ ══════════════════════════════════════►│   for u in channel_members:
      │                                        │     if u in local_registry:
      │  ◄── push {message, unread, typing} ──│       ws.send_json(msg)
      │                                        │
      │  3. POST /api/chat/channels/{id}/      │
      │     messages  (запись в PG) ──────────►│
```

**Почему так, а не «всё через WS»:**
- REST тестируется pytest'ом (WS-хендлеры тяжелее тестировать).
- Сообщение не теряется при обрыве WS — оно уже в БД.
- Идеально ложится на existing FastAPI-инфру (роутеры, Depends, валидация).
- WS остаётся простым: только push новых сообщений, typing, unread-апдейты.

### Точка расширения на multi-worker

Пока работает один uvicorn-воркер — in-memory `CONNECTIONS` реестр достаточен.
При переходе на `web:N` между воркерами встанет **Redis pub/sub**:

```python
# Схема (реализуется в цикле мультитенантности, не сейчас):
# При поступлении сообщения воркер публикует в Redis-канал "chat:federation".
# Каждый воркер подписан и пушит локально-подключённым клиентам.
# Текущий дизайн изолирует fan-out в одну функцию _fanout(channel_id, payload),
# чтобы вставка Redis-прослойки была однострочной.
```

`_fanout()` — точка расширения, которую затронет multi-worker. Это
специально изолированная граница.

> **Второй in-memory компонент — per-user rate limiter — сознательно НЕ
> in-memory, а сразу на Redis** (см. Секцию 6). `CONNECTIONS` невозможно
> вынести в Redis (это живые WS-объекты, не данные), поэтому он остаётся
> локальным с последующим pub/sub-мостом. А вот счётчик сообщений — это просто
> число, и его логично держать в Redis с рождения, чтобы при `web:N` лимит
> «20 msg/мин» не превратился в «20×N». Так известных пробелов до `web:N`
> остаётся ровно один (`_fanout`), и он явный.

---

## Секция 1. Каналы (3 типа)

| Тип | Членство | Пример |
|---|---|---|
| `general` | **вычисляемое**: все staff-роли (admin+manager+employee) | «Общий чат компании» |
| `department` | **вычисляемое по роли** (поле `department_role`) | «Продажи» = manager+employee |
| `topic` | **явное** (таблица `channel_members`) | «Запуск KYK-линейки» |

**Ключевое решение:** каналы `general`/`department` **не хранят участников** —
они вычисляются из роли юзера при запросе/фан-ауте. Новый сотрудник сразу
видит «Общий», без INSERT'ов и рассинхрона. Для произвольных групп — `topic`
с явным списком участников.

**Канал `general`:** ровно один, создаётся сидом при первом запуске миграции.
Каждый staff-юзер автоматически его «видит».

**Каналы `department`:** по одному каналу на роль (`department_role` UNIQUE при
`type='department'`). Членство = `users.role == channels.department_role`.
Например: «Продажи» (`department_role='manager'`), «Сотрудники» (`'employee'`),
«Руководство» (`'admin'`). Создаёт/архивирует admin. UNIQUE-констрейнт на
`(type, department_role)` защищает от дубликатов.

**Каналы `topic`:** создаёт admin/manager, явно добавляет участников. Создатель
автоматически становится участником. Участник может покинуть канал сам.

**Клиенты (`role=client`) не видят чат вообще** — router-guard на фронте +
проверка `role != client` на каждом эндпоинте бэка.

---

## Секция 2. Схема данных

Миграция **009** (по тому же идемпотентному паттерну, что 005-008: `IF NOT EXISTS`,
`information_schema`-проверки). Сиквел ниже — целевой PG-вид; runner обернёт в
idempotent-обёртки.

> **⚠️ Зависимость от версии PG.** `UNIQUE NULLS NOT DISTINCT` требует
> **PostgreSQL 15+** (выпущен конец 2022). Перед применением миграции 009 —
> проверить на деплое: `SELECT version();`. Если PG 13/14 — использовать
> fallback ниже. Это надо сделать на этапе плана, не на этапе применения.

```sql
CREATE TABLE IF NOT EXISTS channels (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('general','department','topic')),
    department_role TEXT NULL,                      -- для type='department'
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived        BOOLEAN NOT NULL DEFAULT false
    -- уникальность department-каналов: см. варианты ниже по версии PG
);
CREATE INDEX IF NOT EXISTS idx_channels_type ON channels (type);
-- department: одна роль = один канал
CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_department_role_unique
    ON channels (department_role) WHERE type = 'department';
-- general: ровно один (department_role IS NULL у general не мешает partial index)
CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_general_unique
    ON channels (id) WHERE type = 'general';

CREATE TABLE IF NOT EXISTS channel_members (
    channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_channel_members_user ON channel_members (user_id);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    content     TEXT NOT NULL CHECK (char_length(content) <= 10000),
    reply_to_id BIGINT NULL REFERENCES messages(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    edited_at   TIMESTAMPTZ NULL,
    deleted_at  TIMESTAMPTZ NULL                       -- soft delete
);
CREATE INDEX IF NOT EXISTS idx_messages_channel_created
    ON messages (channel_id, created_at DESC);
```

**Альтернатива для PG 15+ (если проверка версии подтвердила):** вместо двух
partial-индексов выше — один table-level констрейнт:
```sql
ALTER TABLE channels
    ADD CONSTRAINT channels_unique UNIQUE NULLS NOT DISTINCT (type, department_role);
```
`NULLS NOT DISTINCT` тракует NULL-значения как равные для уникальности, что и
даёт «ровно один general-канал» (где `department_role IS NULL`). На PG 13/14
это синтаксическая ошибка — поэтому миграция 009 использует partial-index
вариант как переносимый. На PG 15+ можно мигрировать на констрейнт.

CREATE TABLE IF NOT EXISTS read_state (
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_id           INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    last_read_message_id BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, channel_id)
);
```

### Дизайн-решения

- **`BIGSERIAL` для `messages.id`** — чат генерит много строк; 32-битный SERIAL
  может переполниться за пару лет активного использования.
- **Soft delete (`deleted_at`)** — сообщения не исчезают физически. Важно для
  документооборота: «что было написано» всегда можно поднять. В ленте рендерится
  как «сообщение удалено».
- **`reply_to_id`** — треды/ответы (один уровень, не рекурсивное дерево — YAGNI).
- **`edited_at`** — пометка редактирования; хранится только последняя версия
  (версионирование — прерогатива Подсистемы III для документов).
- **`read_state.last_read_message_id`** — компактнее, чем таблица «прочитанных
  сообщений» (та росла бы как `messages × users`). Unread-счёт =
  `COUNT(messages.id > last_read_message_id WHERE channel_member)`.
- **`ON DELETE`-политики:** удаление канала каскадно чистит members/messages/
  read_state; удаление юзера обнуляет `author_id` (SET NULL), не убивая историю.
- **REAL `TIMESTAMPTZ`** (в отличие от `VARCHAR` в старых таблицах notes/tasks).
  Чат — новая подсистема, делаем правильно с рождения.
- **`CHECK (char_length(content) <= 10000)`** — верхняя граница на сообщение.
  Без неё единственный вектор (до Подсистемы II) — вставка гигантского блока:
  случайно вставленный лог, скопированная таблица на 500 КБ. Это не только
  раздувает БД, но и летит **целиком в WS-payload всем участникам канала
  синхронно** — при паре таких сообщений фан-аут ощутимо проседает. Двойная
  защита: CHECK на уровне таблицы + `maxlength="10000"` на `<textarea>` фронта.
  10 000 символов ≈ 6-8 абзацев текста — с запасом для любого осмысленного
  сообщения, но достаточно мало, чтобы не стать DoS-вектором.

### Засев `general`-канала

В `db_init.py` (или в теле миграции 009) — после создания `channels`:

```sql
INSERT INTO channels (name, type)
SELECT ('Общий чат', 'general')
WHERE NOT EXISTS (SELECT 1 FROM channels WHERE type = 'general');
```

Идемпотентно. На существующих инсталляциях сработает один раз.

---

## Секция 3. REST API

Все эндпоинты под `Depends(get_current_user)` + проверка `role != "client"` (403).
Паттерн роутер→сервис→БД — как в orders/defects/machinery.

| Метод | Путь | Назначение | Доступ |
|---|---|---|---|
| `GET` | `/api/chat/channels` | Список каналов юзера (general + department его роли + topic где он член), с unread-счётом | staff |
| `POST` | `/api/chat/channels` | Создать topic-канал (тело: name) | admin, manager |
| `GET` | `/api/chat/channels/{id}` | Карточка канала | участник |
| `POST` | `/api/chat/channels/{id}/members` | Добавить участника в topic (тело: user_id) | admin, manager |
| `DELETE` | `/api/chat/channels/{id}/members/{user_id}` | Убрать участника / покинуть | admin, manager (или self) |
| `GET` | `/api/chat/channels/{id}/messages?before={id}&limit=50` | История, курсорная пагинация | участник |
| `POST` | `/api/chat/channels/{id}/messages` | Отправить → сохранение + WS fan-out (тело: content, reply_to_id?) | участник |
| `PATCH` | `/api/chat/messages/{id}` | Редактировать (только автор, ставит edited_at) | автор |
| `DELETE` | `/api/chat/messages/{id}` | Soft-delete (только автор/admin) | автор, admin |
| `POST` | `/api/chat/messages/{id}/read` | Отметить прочитанным (обновляет read_state) | участник канала |
| `GET` | `/api/chat/unread` | Карта `{channel_id: count}` для бейджей | staff |
| `GET` | `/api/chat/members?channel_id=` | Список участников канала (для topic — из `channel_members`; для general/department — вычисляется по роли). Поле `is_online` = есть ли живое WS-соединение в `CONNECTIONS` | участник |
| `POST` | `/api/chat/ws-ticket` | Одноразовый ticket (30с, Redis) для WS-аутентификации | staff |

### Курсорная пагинация истории

`GET /messages?before={message_id}&limit=50` — возвращает 50 сообщений строго
младше `before`. Если `before` не задан — последние 50. Фронт при скролле вверх
берёт `before = oldest_loaded_id`. Это стабильнее оффсет-пагинации (не ломается
при появлении новых сообщений во время скролла).

---

## Секция 4. WebSocket-протокол

### Handshake и аутентификация

Браузерный WebSocket **не может** передать заголовок `Authorization`. Два пути:

- ❌ `?token=xxx` в URL — токен попадает в access-логи nginx, в Referer. Дыра.
- ✅ **ws-ticket**: REST `POST /api/chat/ws-ticket` (с обычным Bearer) →
  короткоживущий ticket (30с, в Redis, одноразовый) → WS коннектится с
  `?ticket=`.

```python
# POST /api/chat/ws-ticket
ticket = secrets.token_urlsafe(32)
redis.setex(f"chat:ws-ticket:{ticket}", 30, str(user_id))

# WS /ws/chat?ticket=...
# GETDEL — атомарная операция (Redis 6.2+). get+delete в две команды создают
# окно гонки: два одновременных хендшейка с одним тикетом (дублирующийся
# реконнект с фронта) оба увидят user_id до того, как первый вызовет delete.
# GETDEL схлопывает get+delete в одну команду — гонка исчезает по конструкции.
user_id = redis.getdel(f"chat:ws-ticket:{ticket}")
if not user_id:
    await ws.close(code=4401); return
CONNECTIONS[int(user_id)].add(ws)
```

Использует **существующий** Redis-клиент (`pdf_service._get_redis`) —
новых зависимостей нет.

### Реестр соединений

```python
# backend/chat_ws.py
CONNECTIONS: dict[int, set[WebSocket]] = defaultdict(set)

async def _fanout(channel_id: int, payload: dict, exclude_user: int | None = None):
    """Точка расширения на multi-worker. Сейчас: локальный fan-out.
    При переходе на web:N сюда встанет redis.publish("chat:federation", ...)."""
    for user_id in members_of(channel_id):
        if user_id == exclude_user:
            continue
        for ws in CONNECTIONS.get(user_id, set()):
            try:
                await ws.send_json(payload)
            except Exception:
                # мёртвое соединение приберётся в heartbeat-цикле
                pass
```

### Сообщения сервер→клиент (JSON)

```json
{ "type": "message",          "channel_id": 3, "message": { "id": 42, "author_id": 7, ... } }
{ "type": "message_edited",   "channel_id": 3, "message": { ... } }
{ "type": "message_deleted",  "channel_id": 3, "message_id": 42 }
{ "type": "unread",           "channel_id": 3, "count": 5 }
{ "type": "typing",           "channel_id": 3, "user_id": 7, "name": "Анна" }
{ "type": "member_joined",    "channel_id": 3, "user_id": 12 }
{ "type": "member_left",      "channel_id": 3, "user_id": 12 }
```

### Сообщения клиент→сервер

```json
{ "type": "typing", "channel_id": 3 }
{ "type": "read",   "channel_id": 3, "message_id": 42 }
```

(Отправка собственно сообщений — через REST, не через WS.)

### Жизненный цикл соединения

- **Heartbeat:** сервер шлёт ping каждые 30с, ждёт pong 60с, иначе закрывает.
- **Реконнект на фронте:** Expo-backoff (1с, 2с, 4с, ... макс 30с).
- **Gap-fill:** при реконнекте клиент шлёт свой последний `last_message_id` по
  каждому каналу → сервер досылает пропущенное (REST `/messages?after=`).
- **Multi-tab:** один юзер может держать несколько WS (набор, не одно значение) —
  сообщение доходит во все его вкладки.

---

## Секция 5. Фронтенд

### Слои

- **Store** `useChatStore` (Pinia, setup-style — как все остальные):
  `channels`, `messagesByChannel: Record<channelId, Message[]>`, `unread`,
  `onlineUsers`, `typingByChannel`. Действия: `loadChannels`, `loadHistory`,
  `sendMessage`, `markRead`, `createTopic`, `addMember`.
- **Composable** `useChatSocket` — менеджер одного WS-соединения (singleton,
  монтируется в `App.vue`). Управляет connect/reconnect/heartbeat, диспетчитизует
  входящие сообщения в store.
- **API** `src/api/chat.ts` — axios-модуль по тому же паттерну, что `users.ts`.

### Layout и роутинг

- Новый раздел **«Чат»** в сайдбаре (`AppSidebar`) — виден только staff-ролям.
- `ChatLayout.vue`: двухпанельный — слева `ChannelList` (с unread-бейджами),
  справа `MessageList` + `MessageInput`.
- Роуты: `/admin/chat`, `/manager/chat`, `/employee/chat` → один и тот же
  `ChatLayout` (как PlanView переиспользуется).

### Компоненты

- `ChannelList.vue` — список каналов с unread-бейджами (`BaseBadge`), индикатор
  активного. Создание topic — через модалку (`useConfirm`-стиль, но для формы —
  своя `BaseModal` или переиспользуем паттерн PersonnelView).
- `MessageList.vue` — лента сообщений. При росте истории — виртуальный скролл
  (`@vueuse/core` `useVirtualList`, уже в зависимостях). Авто-скролл вниз при
  новом сообщении, lazy-load вверх при скролле.
- `MessageInput.vue` — текстареа + кнопка отправки (`BaseButton`). Enter —
  отправить, Shift+Enter — перенос. Эмитит typing-индикатор.
  `maxlength="10000"` (дублирует БД-CHECK — даёт юзеру визуальный лимит).
- `TypingIndicator.vue` — «Анна печатает…» под полем ввода.

### ⚠️ Рендеринг контента — только текстовая интерполяция, никогда `v-html`

`content` — это `TEXT`, который один сотрудник написал и который рендерится в
браузере всех остальных участников канала. **`v-html` здесь запрещён с рождения**
— это мгновенный XSS на ровном месте: достаточно вставить
`<img src=x onerror=...>`, и скрипт выполнится у всех коллег.

`MessageList` рендерит контент **только** через текстовую интерполяцию
`{{ message.content }}` (Vue экранирует HTML по умолчанию). Переносы строк —
через CSS `white-space: pre-wrap` или `style="white-space: pre-wrap"`, а не
через `v-html`/`<br>`-подстановки.

Это правило зафиксировано сейчас, чтобы через месяц — когда в Подсистеме III
появится rich-content — никто не решил «проще вставить `<a href>` прямо в
`content` и сделать `v-html`». Rich-контент будет **отдельным полем/типом
сообщения** (`message_type: 'text' | 'document_link'`), см. «Связь с подсистемами».

### Дизайн-система

Всё на готовой базе: `BaseButton`, `BaseBadge` (unread), `toast` (ошибки),
`ConfirmModal`/`useConfirm` (удаление сообщений). Никаких `alert()`/`prompt()`
— с рождения по новому паттерну.

---

## Секция 6. Обработка ошибок и граничные случаи

| Случай | Поведение |
|---|---|
| Обрыв WS | Авто-реконнект (backoff) + gap-fill через `GET /messages?after=last_id` |
| Получатель офлайн | Сообщение в PG; `unread` обновится при его подключении |
| Удаление сообщения | Soft delete (`deleted_at`), в ленте — «сообщение удалено» |
| Редактирование | Только автор; помечается `(ред.)`; хранится последняя версия |
| Спам | **Новый per-user Redis-лимитер** для чата (НЕ `rate_limiter.py` — тот IP-based, см. ниже): ~20 msg/мин на юзера, 429 при превышении |
| Попытка выйти/удалить участника из `general`/`department` | **400** — членство вычисляемое, строк в `channel_members` нет; редактировать напрямую нельзя (только `topic`) |
| Архивация канала | `archived=true`; не принимает новые сообщения (400), остаётся в истории |
| Не-участник пишет в topic | 403 на `POST /messages` |
| Client-роль стучится к эндпоинту | 403 (проверка на каждом эндпоинте) |
| Несуществующий/архивный канал в WS-fanout | Пропуск (no-op) |
| ping без pong 60с | Сервер закрывает соединение, чистит `CONNECTIONS` |
| Мёртвый WS в реестре | Прибирается heartbeat-циклом и при ошибке `send_json` |

### Per-user лимит сообщений (новый, на Redis)

Существующий `rate_limiter.py` — это **IP-based middleware** (`_store: ip:path ->
timestamps`). Для чата он не годится по двум причинам:

1. **Не тот ключ.** Лимит «20 msg/мин на юзера» требует ключа по `user_id`, а
   не по IP. Офис за одним NAT делит общий IP-лимит — один спамер глушит весь
   офис, и наоборот, офис из 20 менеджеров укладывается в один общий лимит.
2. **Та же single-worker ловушка, что `CONNECTIONS`.** `_store` — in-memory
   `defaultdict`. При переходе на `web:N` лимит «20 msg/мин» фактически станет
   «20×N msg/мин», потому что у каждого воркера свой счётчик.

Поэтому для чата — **отдельный per-user лимитер на Redis** (`INCR` + `EXPIRE`),
который работает корректно и на одном воркере, и на N, без архитектурных
изменений при масштабировании:

```python
# backend/chat_rate_limit.py
def _allow_message(user_id: int) -> bool:
    """Per-user, sliding-window-free fixed window: ~20 msg/min.
    Atomic INCR + first-call EXPIRE — корректно под N воркерами."""
    r = _get_redis()                          # reuse pdf_service client
    key = f"chat:rl:{user_id}:{int(time.time() // 60)}"   # минутный бакет
    count = r.incr(key)
    if count == 1:
        r.expire(key, 120)                    # TTL > окна, чтобы бакет сам чистился
    return count <= 20
```

`POST /api/chat/channels/{id}/messages` вызывает `_allow_message(user_id)` до
записи в БД; при превышении — `429 Too Many Requests` с `Retry-After`.

**Почему фиксированное окно, а не sliding window:** для лимита чата достаточно
приблизительной защиты от флуда; sliding window через `ZREMRANGEBYSCORE`+`ZADD`
точнее, но дороже и сложнее. Фиксированный минутный бакет на `INCR` — 2 команды,
атомарных, дешёвых, и хорошо ложится на Redis. Граничный эффект (всплеск на
стыке двух минут) для чата некритичен.

### Согласованность REST + WS

Гарантия: сообщение, успешно записанное через REST, **точно** будет доставлено.
Доставка идёт best-effort через WS, но пропущенное (офлайн/обрыв) подтянется
через `unread`-счёт и историю. Единственный источник истины — Postgres.

---

## Секция 7. Тестирование

### Backend pytest (расширение ~116 → ~135)

Паттерн — как `test_orders_crud.py` (fixture `db_conn`, monkeypatch `get_db`).

- **`test_chat_channels.py`** (~6): создание topic, листинг видит general/
  department-by-role/topic-by-membership, архивация.
- **`test_chat_messages.py`** (~8): отправка, история (курсорная пагинация),
  редактирование только автором, soft-delete, reply_to.
- **`test_chat_read_state.py`** (~4): markRead обновляет last_read, unread-счёт
  корректен, unread обнуляется после чтения.
- **`test_chat_membership.py`** (~4): добавление/удаление участника topic,
  не-участник не видит сообщения (403), general видят все staff.
- **`test_chat_access.py`** (~3): client-роль получает 403 на всех эндпоинтах.
- **`test_chat_ws.py`** (~4): ws-ticket валиден 30с и одноразовый, WS-хендлер
  регистрирует соединение, `_fanout` доставляет подключённому клиенту (через
  `fastapi.testclient.TestClient.websocket_connect`).

### Frontend vitest

- **`useChatSocket.test.ts`** — мок WebSocket (`vi.mock`), проверка
  connect/reconnect/backoff, диспетчеризация сообщений в store.
- **`chat.test.ts`** (store) — мок axios, проверка loadChannels/sendMessage/
  markRead обновляют состояние.

### Что НЕ автоматизируем

Реальную сетевую задержку, поведение при плохой сети, multi-tab — это ручное
smoke-тестирование (логин двумя юзерами в двух браузерах, обмен сообщениями).

---

## Замечания для фазы реализации

(Не блокируют, но отслеживаются как pitfall'ы в плане.)

- **WS-роут — отдельный `APIRouter`** в `main.py`, не через `register_routes`.
  FastAPI требует `@app.websocket(...)`, а не `@router.websocket` для некоторых
  версий — проверить на этапе плана.
- **`_fanout` вызывает `members_of(channel_id)`** — для general/department это
  запрос к `users WHERE role IN (...)`, для topic — `channel_members JOIN`.
  Кешировать не нужно (вызов только при новой активности, не на каждый тик).
- **Redis-клиент** — переиспользовать `pdf_service._get_redis()` (lazy singleton).
  Не плодить второй пул.
- **nginx** — добавить `proxy_http_version 1.1` + `Upgrade`/`Connection` хедеры
  для `/ws/` location, иначе WS за прокси не поднимется. Это деплой-задача, не код.
- **Старые таблицы (notes/tasks) с `VARCHAR`-таймстампами** — НЕ трогаем. Чат —
  новая подсистема, реальные `TIMESTAMPTZ` только в новых таблицах. Гетча для
  `q()`-адаптера: `db.py` переписывает PG↔SQLite; проверить что новые таблицы
  корректно работают в обоих режимах (или явно PG-only для чата — обосновать).
- **Graceful shutdown** — при `SIGTERM` закрывать все WS корректно (код 1001),
  чтобы клиенты сразу инициировали реконнект, а не ждали heartbeat-таймаута.

---

## Связь с другими подсистемами

- **Подсистема II (вложения):** в `messages` добавится колонка
  `attachment_id` (NULL по умолчанию) — FK к таблице вложений. В Подсистеме I
  эту колонку **не создаём** (YAGNI) — она придёт миграцией II, не трогая
  существующие сообщения.

- **Подсистема III (документооборот):** документ можно «поделиться в канал» —
  создаст сообщение с rich-content-ссылкой на документ. Канал как место
  обсуждения документа. **Важно:** rich-контент НЕ вкладывается HTML'ем в
  `content` (см. запрет `v-html` в Секции 5). Вместо этого в `messages`
  добавится колонка `message_type TEXT DEFAULT 'text'` (`'text' | 'document_link'`)
  и опциональное `payload JSONB` со структурированной ссылкой
  (`{document_id, title, status}`). Фронт рендерит `document_link` отдельным
  типизированным компонентом (`<DocumentLinkCard :payload="msg.payload" />`),
  а не интерполирует HTML. Так XSS-поверхность остаётся нулевой. В Подсистеме I
  эти колонки **не создаём** — придут миграцией III.

- **Мультитенантность (Plan 2):** `tenant_id` добавится в channels/messages/
  channel_members тем же чек-листом из соответствующей спеки. RLS-политики
  ложатся на чат без изменений паттерна.
- **Мультитенантность (Plan 2):** `tenant_id` добавится в channels/messages/
  channel_members тем же чек-листом из соответствующей спеки. RLS-политики
  ложатся на чат без изменений паттерна.
