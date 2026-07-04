# CRM: Чат — Reply (ответ на сообщение) — Design

**Дата:** 2026-07-04
**Статус:** Approved (пользователь одобрил дизайн 2026-07-04)
**Автор совместной сессии:** пользователь + ассистент
**Связанные документы:** `2026-07-04-chat-messaging-design.md` (Подсистема I — фундамент)

## Контекст и проблема

Подсистема I чата (`2026-07-04-chat-messaging-design.md`) задеплоена: каналы,
сообщения, real-time через WebSocket, unread. Но одна из базовых фич чата —
**ответ на сообщение (reply)** — не доведена до конца: UI её показывает
(vue-advanced-chat включает reply по умолчанию), но клик уходит в пустоту,
а backend отдаёт только голый `reply_to_id` без содержимого цитаты.

Фронт рисует пустую цитату. Пользователь не может ответить на конкретное
сообщение — это лишает чат ключевой функции обсуждения контекста.

### Что в дизайн НЕ входит (явный YAGNI)

- **Реакции (emoji)** — отдельная спека позже (требует колонку/таблицу `reactions`,
  свою логику «кто поставил», миграцию). Здесь не трогаем.
- **Аватарки пользователей** — отложены до Личного кабинета + Подсистемы II
  (вложения/файлы), когда появится загрузка изображений. Сейчас в проекте нет
  ни колонки `users.avatar_url`, ни storage — лепить half-measure с инициалами
  решили не стоит (переделывать).
- **Вложенные цитаты** (reply на reply с многоуровневым отображением) —
  только плоская цитата одного уровня. YAGNI.
- **Треды/ветки** (как в Slack) — не делаем, это другая модель коммуникации.
- **Редактирование reply** после отправки — нет.

---

## Решения (из brainstorming с пользователем)

1. **Источник цитаты:** self-join в `list_messages`. Backend одним запросом
   отдаёт для каждого сообщения опциональный `reply_message` с содержимым
   parent'а. Без отдельных запросов с фронта, без гонок при пагинации.

2. **Валидация parent при отправке:** graceful degradation. Если `reply_to_id`
   невалиден (parent не существует, удалён, в другом канале) — **молча обнуляем**
   `reply_to_id` и сохраняем как обычное сообщение. Пользователь не теряет текст
   и не видит ошибку. Принцип fail-soft для UX, fail-closed для данных (в БД
   не появляется битых ссылок).

3. **UX:** нативный vue-advanced-chat. Кнопка «Ответить» появляется при наведении
   на сообщение; цитата рисуется над инпутом с крестиком отмены. Минимум своего
   кода, стандартный паттерн.

---

## Архитектура: поток данных

```
Пользователь наводит на сообщение → vue-advanced-chat показывает стрелку reply
  ↓ клик
ChatView ловит @message-reply { message }
  → vue-advanced-chat сам ставит message в reply-слот над инпутом
  → пользователь пишет текст, жмёт отправку
  ↓
ChatView onSend(event) читает event.detail[0].replyMessage
  → store.sendMessage(channelId, content, replyMessage?._id)
  ↓
POST /api/chat/channels/{id}/messages { content, reply_to_id }
  → backend: если reply_to_id задан — валидируем parent
            (существует AND deleted_at IS NULL AND channel_id совпадает)
            если валиден — INSERT с reply_to_id
            если нет — INSERT без reply_to_id (graceful)
  → returns message (с reply_message, если parent валиден)
  → WS fan-out остальным участникам
```

На чтении `list_messages` делает self-join и отдаёт `reply_message` для каждого
сообщения. Фронт через адаптер транслирует это в формат vue-advanced-chat.

---

## Backend изменения

### 1. `list_messages` — self-join (`services/chat_service.py`)

Расширить SELECT: к существующему `LEFT JOIN users u ON u.id = m.author_id`
добавить parent + автора parent:

```sql
SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
       m.created_at, m.edited_at, m.deleted_at,
       u.username, u.name,                              -- r[8..9] автор
       p.id, p.content, p.author_id, pu.name, p.deleted_at  -- r[10..14] parent
FROM messages m
LEFT JOIN users u  ON u.id  = m.author_id
LEFT JOIN messages p ON p.id = m.reply_to_id           -- цитируемое сообщение
LEFT JOIN users pu  ON pu.id = p.author_id             -- автор цитаты
WHERE m.channel_id = %s [AND m.id < %s]
ORDER BY m.id DESC LIMIT %s
```

**Почему LEFT JOIN для parent:** если `reply_to_id` был обнулён (или parent
удалён физически, хотя у нас soft-delete) — `p.*` будет NULL, `reply_message`
получится `null`, фронт не рисует цитату. Сообщение остаётся. Без crash.

**Индексы:** существующий `idx_messages_channel_created` покрывает выборку по
каналу; self-join по `p.id` (= PK) бесплатен. Новых индексов не нужно.

### 2. `_message_row_to_dict` — новое поле `reply_message`

```python
def _message_row_to_dict(r) -> Dict[str, Any]:
    # r[10..14] — parent (p.id, p.content, p.author_id, pu.name, p.deleted_at)
    reply_message = None
    if r[10] is not None and r[14] is None:  # parent существует и не удалён
        reply_message = {
            "id": r[10],
            "content": r[11],
            "author_id": r[12],
            "author_name": r[13],
        }
    return {
        "id": r[0],
        "channel_id": r[1],
        "author_id": r[2],
        "content": r[3],
        "reply_to_id": r[4],                  # остаётся как есть (для фронт-кеша)
        "created_at": ...,
        "edited_at": ...,
        "deleted_at": ...,
        "author_username": r[8],
        "author_name": r[9],
        "reply_message": reply_message,        # НОВОЕ
    }
```

**Нюанс:** `reply_to_id` и `reply_message` дублируют информацию частично, но
несут разный смысл: `reply_to_id` — это id для фронт-кеша/восстановления
контекста, `reply_message` — готовая цитата для отображения. Оставляем оба.

### 3. `send_message` — валидация parent + graceful обнуление

```python
async def send_message(channel_id, data, current_user):
    ...
    reply_to_id = data.reply_to_id
    if reply_to_id is not None:
        cur.execute(
            q("SELECT 1 FROM messages WHERE id = %s AND channel_id = %s AND deleted_at IS NULL"),
            (reply_to_id, channel_id),
        )
        if cur.fetchone() is None:
            # graceful: parent невалиден → отправляем как обычное сообщение
            reply_to_id = None
    cur.execute(
        q("""INSERT INTO messages (channel_id, author_id, content, reply_to_id)
             VALUES (%s, %s, %s, %s) RETURNING id, created_at"""),
        (channel_id, current_user["id"], data.content, reply_to_id),
    )
    ...
```

После INSERT — если `reply_to_id` валиден, достать parent (content, author_name)
и вернуть `reply_message` в ответе, чтобы WS fanout и отправитель получили
готовую цитату без повторного запроса.

**Почему не returning с join:** проще двумя простыми SELECT'ами (один для
валидации, один для построения ответа), чем один сложный. Код читаемее.

### 4. Без миграции

Колонка `messages.reply_to_id BIGINT NULL REFERENCES messages(id) ON DELETE SET NULL`
уже существует (миграция 009, строка с `reply_to_id`). Schema `MessageCreate.reply_to_id`
тоже уже есть (`schemas/chat.py:16`). Меняем только SQL в service-функциях.

---

## Frontend изменения

### 1. `types/chat.ts` — расширить ChatMessage

```typescript
export interface ChatMessage {
  // ...существующие поля...
  reply_message?: {
    id: number
    content: string
    author_id: number | null
    author_name: string | null
  } | null
}
```

### 2. `composables/useChatAdapter.ts` — `toMessage`

```typescript
export function toMessage(m): VACMessage {
  // ...существующий код...
  replyMessage: m.reply_message
    ? {
        _id: String(m.reply_message.id),
        content: m.reply_message.content,
        senderId: String(m.reply_message.author_id ?? ''),
        username: m.reply_message.author_name ?? 'Неизвестно',
      }
    : null,
}
```

Раньше здесь формировался `replyMessage` из голого `reply_to_id` с пустыми
`content`/`senderId` — теперь из полноценного `reply_message`.

### 3. `views/ChatView.vue` — обработчики reply

Добавить привязки событий:
```html
<vue-advanced-chat
  ...
  @send-message="onSend"
  @message-reply="onReply"
/>
```

```typescript
function onReply(_event: any) {
  // vue-advanced-chat сам поместит выбранное сообщение в reply-слот над
  // инпутом. Нам нужно только обработать отправку — replyMessage придёт
  // в event.detail[0] onSend.
}

function onSend(event: any) {
  const { content, roomId, replyMessage } = event.detail[0]
  store.sendMessage(Number(roomId), content, replyMessage?._id)
}
```

### 4. `stores/chat.ts` — sendMessage принимает replyToId

```typescript
async function sendMessage(channelId: number, content: string, replyToId?: number) {
  const { data } = await chatApi.sendMessage(channelId, { content, reply_to_id: replyToId })
  messagesByChannel.value[channelId] = [...(messagesByChannel.value[channelId] ?? []), data]
  unread.value[channelId] = 0
}
```

### 5. `api/chat.ts` — проброс reply_to_id

```typescript
sendMessage: (channelId, body: { content: string; reply_to_id?: number }) =>
  api.post(`/api/chat/channels/${channelId}/messages`, body),
```

(сейчас шлёт только `{ content }` — расширяем тело, не ломая контракт).

---

## Обработка ошибок и edge cases

| Случай | Поведение |
|---|---|
| Parent удалён при **чтении** | `LEFT JOIN` → `p.*` NULL → `reply_message: null` → фронт не рисует цитату, сообщение остаётся. Без crash. |
| Parent удалён при **записи** | Валидация ловит → `reply_to_id` обнуляется → обычное сообщение. |
| Parent в другом канале | Валидация (`channel_id = %s`) ловит → обнуляется. |
| Parent не существует (id=99999) | Валидация ловит → обнуляется. |
| Reply на своё сообщение | Разрешено. Без ограничений self-reply. |
| `reply_to_id = 0` | Pydantic пропустит `0`; валидация (parent с id=0 нет) → обнуление. |
| Глубина reply | Один уровень (плоская цитата). Вложенных нет — это намеренно. |
| WS fanout | Транслирует message целиком (с `reply_message`), клиентам не нужно дораспрашивать. |

---

## Тестирование (TDD, по образцу существующих `test_chat_*.py`)

### Backend (pytest)

| # | Тест | Что проверяет |
|---|---|---|
| 1 | `test_list_messages_includes_reply_message` | parent отдаётся в `reply_message` с content/author_name |
| 2 | `test_send_message_with_valid_reply` | сообщение создаётся с `reply_to_id`, ответ содержит `reply_message` |
| 3 | `test_send_message_reply_to_deleted_parent` | `reply_to_id` обнуляется (graceful) |
| 4 | `test_send_message_reply_to_other_channel` | `reply_to_id` обнуляется (parent в другом канале) |
| 5 | `test_send_message_reply_to_nonexistent` | `reply_to_id` обнуляется (parent не существует) |
| 6 | `test_list_messages_reply_to_deleted_parent` | `reply_message: null`, не падает |

### Frontend (vitest)

| # | Тест | Что проверяет |
|---|---|---|
| 7 | `toMessage maps reply_message when present` | цитата транслируется в формат VAC |
| 8 | `toMessage returns null replyMessage when absent` | нет цитаты → null, не undefined |

Ожидаемый счёт: 154 → 162 backend + 2 фронт (5 → 7).

---

## Порядок реализации (TDD-циклы)

1. Backend test 1 (красный) → `list_messages` self-join + `_message_row_to_dict` → зелёный.
2. Backend test 2 → `send_message` валидация + `reply_message` в ответе → зелёный.
3. Backend tests 3–6 → все пути graceful degradation → зелёные.
4. Frontend tests 7–8 → адаптер → зелёные.
5. ChatView wiring (`@message-reply` + `replyMessage` в `onSend`).
6. Store + api проброс `reply_to_id`.
7. Ручная проверка в браузере (открыть `/admin/chat`, ответить на сообщение).
8. Билд (`npm run build`) + backend pytest полный прогон.

---

## Риски и компромиссы

- **Self-join утяжеляет `list_messages`** — теоретически. На практике parent
  берётся по PK (`p.id`), выборка по каналу уже покрыта индексом
  `idx_messages_channel_created`. На объёмах чата CRM (сотни, не миллионы
  сообщений) — пренебрежимо.
- **`reply_to_id` и `reply_message` дублируют смысл** — осознанный компромисс:
  id нужен для фронт-кеша, объект — для отображения. Альтернатива (убрать id,
  оставить только объект) ломает обратную совместимость с уже отдающимся полем.
- **Graceful vs 400** — выбрали soft, чтобы не фрустрировать пользователя
  (текст не теряется). Платим: в БД могут копиться сообщения без reply,
  хотя пользователь «отвечал». Это приемлемо — визуально они выглядят как обычные.

---

*Спека написана с любовью. 💕 Канарейка жива.*
