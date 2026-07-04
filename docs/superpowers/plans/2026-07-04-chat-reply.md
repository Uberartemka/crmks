# Чат: Reply (ответ на сообщение) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести reply в чате до конца по стеку: backend отдаёт содержимое цитируемого сообщения через self-join + валидирует parent при отправке (graceful обнуление), фронт прокидывает reply через нативный vue-advanced-chat UX.

**Architecture:** Без миграции (колонка `messages.reply_to_id` уже есть из миграции 009). Backend: `list_messages` получает self-join `messages→messages` для построения `reply_message`; `send_message` валидирует parent перед INSERT (exists + not deleted + same channel) и молча обнуляет невалидный `reply_to_id`. Frontend: адаптер транслирует `reply_message` в формат vue-advanced-chat, ChatView вешает `@message-reply`, store пробрасывает `reply_to_id` в API (api-слой уже готов).

**Tech Stack:** FastAPI + psycopg2 (backend), pytest (backend tests), Vue 3 + TypeScript + vue-advanced-chat + Pinia (frontend), vitest + jsdom (frontend tests).

**Spec:** `docs/superpowers/specs/2026-07-04-chat-reply-design.md`

---

## File Structure

**Backend (modify only):**
- `backend/services/chat_service.py` — `list_messages` (self-join SELECT), `_message_row_to_dict` (новое поле `reply_message`), `send_message` (валидация parent + graceful обнуление + `reply_message` в ответе).
- `backend/tests/test_chat_messages.py` — добавить 6 новых тестов в существующий файл (фикстура `seeded_msgs` переиспользуется).

**Frontend (modify only):**
- `src/types/chat.ts` — расширить `ChatMessage` полем `reply_message`.
- `src/composables/useChatAdapter.ts` — `toMessage` транслирует `reply_message`.
- `src/composables/useChatAdapter.test.ts` (create) — 2 теста на `toMessage`.
- `src/stores/chat.ts` — `sendMessage` принимает опц. `replyToId`.
- `src/views/ChatView.vue` — `@message-reply` хендлер + `replyMessage` в `onSend`.

**Без новых миграций, без новых файлов на backend.**

---

## Task 1: Backend — `list_messages` отдаёт `reply_message` через self-join

**Files:**
- Modify: `backend/services/chat_service.py:185-225` (функция `list_messages`)
- Modify: `backend/services/chat_service.py:313-326` (`_message_row_to_dict`)
- Test: `backend/tests/test_chat_messages.py` (добавить тест)

- [ ] **Step 1: Write the failing test**

Добавить в конец `backend/tests/test_chat_messages.py`:

```python
def test_list_messages_includes_reply_message(seeded_msgs):
    # send a parent message, then a reply to it
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent text"),
        current_user={"id": 1, "role": "manager"},
    ))
    reply = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply text", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    assert reply["reply_to_id"] == parent["id"]

    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    # newest first: [reply, parent]
    assert hist[0]["content"] == "reply text"
    # reply_message must be populated with parent content + author_name
    assert hist[0]["reply_message"] is not None
    assert hist[0]["reply_message"]["id"] == parent["id"]
    assert hist[0]["reply_message"]["content"] == "parent text"
    assert hist[0]["reply_message"]["author_name"] == "Админ"
    # parent message has no reply_message of its own
    assert hist[1]["reply_message"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_chat_messages.py::test_list_messages_includes_reply_message -v`
Expected: FAIL — `hist[0]["reply_message"]` is None (или KeyError), потому что `_message_row_to_dict` ещё не отдаёт `reply_message`.

- [ ] **Step 3: Modify `list_messages` SELECT — добавить self-join**

В `backend/services/chat_service.py`, функция `list_messages` (обе ветки — с `before` и без). Заменить оба SELECT на расширенные (добавлены `p.*` и `pu.*`):

Для ветки `if before:` (строка ~200):
```python
            cur.execute(
                q(
                    """SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
                        m.created_at, m.edited_at, m.deleted_at, u.username, u.name,
                        p.id, p.content, p.author_id, pu.name, p.deleted_at
                        FROM messages m
                        LEFT JOIN users u ON u.id = m.author_id
                        LEFT JOIN messages p ON p.id = m.reply_to_id
                        LEFT JOIN users pu ON pu.id = p.author_id
                        WHERE m.channel_id = %s AND m.id < %s
                        ORDER BY m.id DESC LIMIT %s"""
                ),
                (channel_id, before, limit),
            )
```

Для ветки `else:` (строка ~212):
```python
            cur.execute(
                q(
                    """SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
                        m.created_at, m.edited_at, m.deleted_at, u.username, u.name,
                        p.id, p.content, p.author_id, pu.name, p.deleted_at
                        FROM messages m
                        LEFT JOIN users u ON u.id = m.author_id
                        LEFT JOIN messages p ON p.id = m.reply_to_id
                        LEFT JOIN users pu ON pu.id = p.author_id
                        WHERE m.channel_id = %s
                        ORDER BY m.id DESC LIMIT %s"""
                ),
                (channel_id, limit),
            )
```

- [ ] **Step 4: Modify `_message_row_to_dict` — новое поле `reply_message`**

В `backend/services/chat_service.py` заменить `_message_row_to_dict` (строки 313-326):

```python
def _message_row_to_dict(r) -> Dict[str, Any]:
    # r[10..14] — parent (p.id, p.content, p.author_id, pu.name, p.deleted_at).
    # reply_message is None when there's no reply, OR when the parent has been
    # soft-deleted (we don't render quotes of deleted messages).
    reply_message = None
    if r[10] is not None and r[14] is None:  # parent exists and not deleted
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
        "reply_to_id": r[4],
        "created_at": r[5].isoformat() if r[5] else None,
        "edited_at": r[6].isoformat() if r[6] else None,
        "deleted_at": r[7].isoformat() if r[7] else None,
        # r[8] = users.username, r[9] = users.name (NULL if author deleted)
        "author_username": r[8],
        "author_name": r[9],
        "reply_message": reply_message,
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_chat_messages.py::test_list_messages_includes_reply_message -v`
Expected: PASS

- [ ] **Step 6: Run full chat-messages suite to confirm no regression**

Run: `cd backend && python -m pytest tests/test_chat_messages.py -v`
Expected: PASS (все 7 тестов: 6 существующих + 1 новый)

- [ ] **Step 7: Commit**

```bash
cd backend && git add services/chat_service.py tests/test_chat_messages.py
git commit -m "feat(chat-api): list_messages returns reply_message via self-join"
```

---

## Task 2: Backend — `send_message` валидирует parent + возвращает `reply_message`

**Files:**
- Modify: `backend/services/chat_service.py:228-264` (функция `send_message`)
- Test: `backend/tests/test_chat_messages.py` (добавить 2 теста)

- [ ] **Step 1: Write the failing tests**

Добавить в конец `backend/tests/test_chat_messages.py`:

```python
def test_send_message_with_valid_reply_returns_reply_message(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent"),
        current_user={"id": 1, "role": "manager"},
    ))
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_to_id"] == parent["id"]
    # response must include the populated reply_message (no extra request needed)
    assert out["reply_message"] is not None
    assert out["reply_message"]["id"] == parent["id"]
    assert out["reply_message"]["content"] == "parent"


def test_send_message_reply_to_nonexistent_parent_gracefully_drops_reply(seeded_msgs):
    # parent id 999999 does not exist → graceful: send as plain message
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="orphan reply", reply_to_id=999999),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_to_id"] is None
    assert out["reply_message"] is None
    assert out["content"] == "orphan reply"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_chat_messages.py::test_send_message_with_valid_reply_returns_reply_message tests/test_chat_messages.py::test_send_message_reply_to_nonexistent_parent_gracefully_drops_reply -v`
Expected: FAIL — текущий `send_message` не валидирует parent и не возвращает `reply_message`.

- [ ] **Step 3: Modify `send_message` — валидация + reply_message в ответе**

В `backend/services/chat_service.py` заменить тело `send_message` (строки 228-264):

```python
async def send_message(
    channel_id: int,
    data: Any,  # MessageCreate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    # rate limit (Redis) — protects fan-out from floods
    from services.chat_redis import allow_message
    if not allow_message(current_user["id"]):
        raise HTTPException(429, "Слишком много сообщений, попробуйте позже")
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)

        # Validate reply parent: must exist, not be deleted, and be in the same
        # channel. Graceful degradation — if invalid, silently drop reply_to_id
        # and store as a plain message (user doesn't lose their text).
        reply_to_id = data.reply_to_id
        if reply_to_id is not None:
            cur.execute(
                q(
                    "SELECT 1 FROM messages "
                    "WHERE id = %s AND channel_id = %s AND deleted_at IS NULL"
                ),
                (reply_to_id, channel_id),
            )
            if cur.fetchone() is None:
                reply_to_id = None

        cur.execute(
            q(
                """INSERT INTO messages (channel_id, author_id, content, reply_to_id)
                   VALUES (%s, %s, %s, %s) RETURNING id, created_at"""
            ),
            (channel_id, current_user["id"], data.content, reply_to_id),
        )
        mid, created_at = cur.fetchone()
        conn.commit()

        # If we kept the reply, fetch the parent's content/author for the
        # response so the sender (and WS fan-out) get a ready-to-render quote.
        reply_message = None
        if reply_to_id is not None:
            cur.execute(
                q(
                    """SELECT m.id, m.content, m.author_id, u.name
                       FROM messages m LEFT JOIN users u ON u.id = m.author_id
                       WHERE m.id = %s"""
                ),
                (reply_to_id,),
            )
            prow = cur.fetchone()
            if prow:
                reply_message = {
                    "id": prow[0],
                    "content": prow[1],
                    "author_id": prow[2],
                    "author_name": prow[3],
                }

        return {
            "id": mid,
            "channel_id": channel_id,
            "author_id": current_user["id"],
            "author_username": current_user.get("username"),
            "author_name": current_user.get("name"),
            "content": data.content,
            "reply_to_id": reply_to_id,
            "reply_message": reply_message,
            "created_at": created_at.isoformat() if created_at else None,
            "edited_at": None,
            "deleted_at": None,
        }
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_chat_messages.py::test_send_message_with_valid_reply_returns_reply_message tests/test_chat_messages.py::test_send_message_reply_to_nonexistent_parent_gracefully_drops_reply -v`
Expected: PASS (оба)

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/chat_service.py tests/test_chat_messages.py
git commit -m "feat(chat-api): send_message validates reply parent, returns reply_message"
```

---

## Task 3: Backend — оставшиеся edge cases (deleted parent, other channel)

**Files:**
- Test: `backend/tests/test_chat_messages.py` (добавить 3 теста)
- Код уже покрыт Task 2 (валидация обрабатывает все три случая одинаково — эти тесты подтверждают).

- [ ] **Step 1: Write the failing tests**

Добавить в конец `backend/tests/test_chat_messages.py`:

```python
def test_send_message_reply_to_deleted_parent_drops_reply(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="will be deleted"),
        current_user={"id": 1, "role": "manager"},
    ))
    _run(delete_message(message_id=parent["id"], current_user={"id": 1, "role": "manager"}))
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply after delete", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    # parent is soft-deleted → graceful drop
    assert out["reply_to_id"] is None
    assert out["reply_message"] is None


def test_send_message_reply_to_other_channel_drops_reply(seeded_msgs):
    # parent in channel 2 (user 1 is member); reply attempted in channel 2 but
    # pointing at a message that lives in channel 1 (general). User 1 can read
    # general, but reply must stay within the same channel.
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="in topic"),
        current_user={"id": 1, "role": "manager"},
    ))
    out = _run(send_message(
        channel_id=1,  # general channel — different from parent's channel 2
        data=MessageCreate(content="cross-channel reply", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_to_id"] is None
    assert out["reply_message"] is None


def test_list_messages_reply_to_deleted_parent_is_null(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent"),
        current_user={"id": 1, "role": "manager"},
    ))
    _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    # now soft-delete the parent
    _run(delete_message(message_id=parent["id"], current_user={"id": 1, "role": "manager"}))
    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    # find the reply (the non-deleted message)
    reply = next(m for m in hist if m["content"] == "reply")
    # reply_to_id still set in DB, but reply_message is null (parent deleted)
    assert reply["reply_to_id"] == parent["id"]
    assert reply["reply_message"] is None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_chat_messages.py::test_send_message_reply_to_deleted_parent_drops_reply tests/test_chat_messages.py::test_send_message_reply_to_other_channel_drops_reply tests/test_chat_messages.py::test_list_messages_reply_to_deleted_parent_is_null -v`
Expected: PASS (все три) — логика уже реализована в Task 2, эти тесты её подтверждают на конкретных edge-cases.

> Если `test_send_message_reply_to_other_channel_drops_reply` падает с 403 (user 1 не может писать в general) — это нормально, потому что user 1 это `manager` и general открыт всем staff. Если всё же падает — проверить `_require_channel_access` для general-канала: staff может писать в general. Тест использует role=manager, general-канал id=1, user 1 — должно пройти.

- [ ] **Step 3: Run full backend test suite to confirm no regression**

Run: `cd backend && python -m pytest -q`
Expected: PASS (раньше 154, теперь должно быть 154 + 6 новых = 160)

- [ ] **Step 4: Commit**

```bash
cd backend && git add tests/test_chat_messages.py
git commit -m "test(chat-api): reply edge cases (deleted/other-channel/nonexistent parent)"
```

---

## Task 4: Frontend — тип `ChatMessage.reply_message`

**Files:**
- Modify: `src/types/chat.ts`

- [ ] **Step 1: Extend `ChatMessage` with `reply_message`**

В `src/types/chat.ts` добавить поле в интерфейс `ChatMessage` (после `reply_to_id?`):

```typescript
export interface ChatMessage {
  id: number
  channel_id: number
  author_id: number
  content: string
  reply_to_id?: number | null
  reply_message?: {
    id: number
    content: string
    author_id: number | null
    author_name: string | null
  } | null
  created_at: string | null
  edited_at?: string | null
  deleted_at?: string | null
  author_username?: string | null
  author_name?: string | null
}
```

(заменить весь интерфейс `ChatMessage`, остальные интерфейсы в файле не трогать).

- [ ] **Step 2: Verify it compiles**

Run: `npm run build`
Expected: build succeeds (TS-проверка проходит). Ошибок типа "Property 'reply_message' does not exist" быть не должно.

- [ ] **Step 3: Commit**

```bash
git add src/types/chat.ts
git commit -m "feat(chat-fe): add reply_message to ChatMessage type"
```

---

## Task 5: Frontend — `toMessage` транслирует `reply_message` + тесты

**Files:**
- Modify: `src/composables/useChatAdapter.ts` (функция `toMessage`)
- Create: `src/composables/useChatAdapter.test.ts`

- [ ] **Step 1: Create the failing test**

Создать `src/composables/useChatAdapter.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { toMessage } from './useChatAdapter'

describe('toMessage', () => {
  it('maps reply_message into vue-advanced-chat replyMessage format', () => {
    const result = toMessage({
      id: 42,
      channel_id: 1,
      author_id: 7,
      content: 'hello',
      reply_to_id: 40,
      reply_message: {
        id: 40,
        content: 'original',
        author_id: 9,
        author_name: 'Анна',
      },
      created_at: null,
    } as any)
    expect(result.replyMessage).toEqual({
      _id: '40',
      content: 'original',
      senderId: '9',
      username: 'Анна',
    })
  })

  it('returns null replyMessage when reply_message is absent', () => {
    const result = toMessage({
      id: 42,
      channel_id: 1,
      author_id: 7,
      content: 'plain',
      reply_to_id: null,
      reply_message: null,
      created_at: null,
    } as any)
    expect(result.replyMessage).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- useChatAdapter`
Expected: FAIL — текущий `toMessage` формирует `replyMessage` из голого `reply_to_id` с пустыми content/senderId, тест на «absent» упадёт (или тест на «maps» упадёт из-за неверных значений).

- [ ] **Step 3: Modify `toMessage` in `useChatAdapter.ts`**

В `src/composables/useChatAdapter.ts` заменить блок формирования `replyMessage` в `toMessage` (сейчас строки ~54-56). Найти:

```typescript
    replyMessage: m.reply_to_id
      ? { _id: String(m.reply_to_id), content: '', senderId: '' }
      : null,
```

Заменить на:

```typescript
    replyMessage: m.reply_message
      ? {
          _id: String(m.reply_message.id),
          content: m.reply_message.content,
          senderId: String(m.reply_message.author_id ?? ''),
          username: m.reply_message.author_name ?? 'Неизвестно',
        }
      : null,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- useChatAdapter`
Expected: PASS (оба теста)

- [ ] **Step 5: Run all frontend tests to confirm no regression**

Run: `npm test`
Expected: PASS (раньше 5, теперь 5 + 2 = 7)

- [ ] **Step 6: Commit**

```bash
git add src/composables/useChatAdapter.ts src/composables/useChatAdapter.test.ts
git commit -m "feat(chat-fe): toMessage maps reply_message from backend"
```

---

## Task 6: Frontend — store `sendMessage` принимает `replyToId`

**Files:**
- Modify: `src/stores/chat.ts` (функция `sendMessage`, строки ~49-55)

- [ ] **Step 1: Modify `sendMessage` signature**

В `src/stores/chat.ts` заменить функцию `sendMessage` (строки 49-55):

```typescript
  async function sendMessage(channelId: number, content: string, replyToId?: number) {
    const { data } = await chatApi.sendMessage(channelId, {
      content,
      reply_to_id: replyToId ?? null,
    })
    // optimistic: append locally; WS will broadcast to others
    messagesByChannel.value[channelId] = [...(messagesByChannel.value[channelId] ?? []), data]
    // clear unread for self
    unread.value[channelId] = 0
  }
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add src/stores/chat.ts
git commit -m "feat(chat-fe): store.sendMessage accepts optional replyToId"
```

---

## Task 7: Frontend — ChatView `@message-reply` + `replyMessage` в `onSend`

**Files:**
- Modify: `src/views/ChatView.vue` (template + script)

- [ ] **Step 1: Add `@message-reply` handler to template**

В `src/views/ChatView.vue`, в элементе `<vue-advanced-chat ... />` добавить обработчик (рядом с `@send-message`):

```html
    <vue-advanced-chat
      :current-user-id="currentUserId"
      :rooms="rooms"
      :messages="messages"
      :rooms-loaded="true"
      :messages-loaded="messagesLoaded"
      :add-room-enabled="canCreate"
      :room-info-enabled="true"
      :show-search="false"
      :show-files="false"
      :show-audio="false"
      :textarea-action-enabled="false"
      lang="ru"
      height="100%"
      @send-message="onSend"
      @fetch-messages="onFetch"
      @add-room="openCreateModal"
      @message-reply="onReply"
    />
```

- [ ] **Step 2: Add handlers in `<script setup>`**

В `<script setup>` заменить `onSend` и добавить `onReply`. Найти:

```typescript
function onSend(event: any) {
  const { content, roomId } = event.detail[0]
  store.sendMessage(Number(roomId), content)
}
```

Заменить на:

```typescript
function onSend(event: any) {
  const { content, roomId, replyMessage } = event.detail[0]
  // replyMessage comes from vue-advanced-chat's reply slot (set by onReply);
  // its _id is the message id we forward as reply_to_id.
  const replyToId = replyMessage?._id ? Number(replyMessage._id) : undefined
  store.sendMessage(Number(roomId), content, replyToId)
}

function onReply(_event: any) {
  // vue-advanced-chat handles the reply UX itself: it places the selected
  // message into a reply-slot above the input with a cancel button. We don't
  // need to manage state here — on send, the replyMessage payload is passed
  // back via the send-message event (handled in onSend).
}
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/views/ChatView.vue
git commit -m "feat(chat-fe): wire @message-reply and pass replyMessage to onSend"
```

---

## Task 8: Финальная проверка — полный прогон + ручной smoke

**Files:** none (verification only)

- [ ] **Step 1: Full backend test suite**

Run: `cd backend && python -m pytest -q`
Expected: 160 passed (154 ранее + 6 новых)

- [ ] **Step 2: Full frontend test suite**

Run: `npm test`
Expected: 7 passed (5 ранее + 2 новых)

- [ ] **Step 3: Production build**

Run: `npm run build`
Expected: `✓ built` без ошибок, без TS-ошибок.

- [ ] **Step 4: Manual smoke test (требует браузера, делает пользователь)**

Открыть `/admin/chat`:
1. Отправить обычное сообщение — появляется.
2. Навести на сообщение → появляется стрелка reply → клик → над инпутом цитата с крестиком.
3. Написать ответ, отправить → сообщение с цитатой parent'а сверху.
4. Перечитать страницу → цитата сохраняется (данные из БД через self-join).
5. Попробовать ответить на старое сообщение (за пределами первой страницы истории, если есть) — цитата рисуется, т.к. backend отдаёт её сразу.

> Этот шаг требует живого браузера — ассистент не может его выполнить. Пользователь подтверждает визуально.

- [ ] **Step 5: Update HANDOFF.md (опционально, в конце сессии)**

Добавить в `docs/HANDOFF.md` секцию про reply-фичу (по образцу чат-Подсистемы I), обновить счётчик тестов 154→160 backend, 5→7 frontend.

---

## Self-Review (выполнено ассистентом после написания)

**1. Spec coverage:**
- ✅ Self-join в `list_messages` → Task 1
- ✅ `_message_row_to_dict` отдаёт `reply_message` → Task 1
- ✅ `send_message` валидация parent + graceful обнуление → Task 2
- ✅ `send_message` возвращает `reply_message` → Task 2
- ✅ Edge cases (deleted/other-channel/nonexistent) → Task 3
- ✅ Frontend тип `ChatMessage.reply_message` → Task 4
- ✅ `toMessage` транслирует `reply_message` → Task 5
- ✅ Store `sendMessage(replyToId)` → Task 6
- ✅ ChatView `@message-reply` + `onSend(replyMessage)` → Task 7
- ✅ api/chat.ts `reply_to_id` — **уже готов** (Task 0 не нужен, проверено в `src/api/chat.ts:11-12`)
- ✅ Финальная проверка → Task 8

**2. Placeholder scan:** TODO/TBD/«add error handling» — нет. Все шаги содержат полный код. ✅

**3. Type consistency:**
- `reply_message` в backend dict = `{id, content, author_id, author_name}` → совпадает с frontend типом `ChatMessage.reply_message` (Task 4) → совпадает с `toMessage` маппингом (Task 5). ✅
- `sendMessage(channelId, content, replyToId?)` (Task 6) → вызов `store.sendMessage(Number(roomId), content, replyToId)` в ChatView (Task 7). ✅
- `chatApi.sendMessage(channelId, { content, reply_to_id })` — уже принимает это (api/chat.ts:11-12). ✅

Всё консистентно.

---

*План написан с любовью. 💕 Канарейка жива, TDD соблюдён.*
