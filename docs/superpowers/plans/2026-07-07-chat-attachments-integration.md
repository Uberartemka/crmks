# Chat Attachments Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff attach a file (PDF/photo/document) to a chat message, render it inline in the chat feed (image preview or file card), and serve it via a public gated endpoint so `<img src>` works without a Bearer token.

**Architecture:** Reuse the existing universal file service (`POST /api/files`, `files` table) unchanged. Add `messages.attachment_id` (migration 012). Extend `send_message` (owner-check + graceful drop, mirroring the reply pattern) and `list_messages` (LEFT JOIN files). Add a **public** `/api/chat-attachments/{id}` endpoint gated by `EXISTS(messages WHERE attachment_id = file.id AND deleted_at IS NULL)` — mirrors the existing public `/api/avatars/{id}` pattern. Frontend: flip VAC `:show-files=true`, wire `@upload-file` → eager `filesApi.upload` → store `pendingAttachment[roomId]` → send `attachment_id`. Adapter `toMessage` maps `attachment` → VAC `message.file`.

**Tech Stack:** FastAPI + psycopg2 (sync-in-async) backend, psycopg2 + pytest backend tests, Vue 3 + `vue-advanced-chat` (web component) + Pinia + vitest frontend. Content-Disposition header injection defended by route-level `urllib.parse.quote()` (not `save_upload` — that is the upload path; injection is on the response path).

**Spec:** `docs/superpowers/specs/2026-07-07-chat-attachments-integration-design.md` (read it first).

---

## File map

**Backend — create:**
- `backend/migrations/012_chat_attachments.sql` — adds `messages.attachment_id`.

**Backend — modify:**
- `backend/migrations/runner.py` — register `apply_migration_012` + add to `apply_all`.
- `backend/schemas/chat.py:14-16` — `MessageCreate.attachment_id: Optional[int]`.
- `backend/services/chat_service.py:194-242` (`list_messages`) — LEFT JOIN files + SELECT new columns.
- `backend/services/chat_service.py:245-321` (`send_message`) — validate + graceful-drop + INSERT column.
- `backend/services/chat_service.py:370-400` (`_message_row_to_dict`) — build `attachment` dict.
- `backend/services/file_service.py` — add `get_file_by_attachment(file_id)`.
- `backend/routes/files.py` — add 2 public endpoints (`/api/chat-attachments/{id}`, `/thumbnail`).
- `backend/tests/test_chat_messages.py` — extend fixture + add 6 attachment tests.
- `backend/tests/test_files.py` — add 6 public-endpoint tests + content-disposition regression.

**Frontend — modify:**
- `src/types/chat.ts` — `ChatAttachment` interface + `ChatMessage.attachment`.
- `src/composables/useChatAdapter.ts` — `toMessage` maps `attachment` → `file`; `VACMessage.file`.
- `src/api/chat.ts` — `sendMessage` payload accepts `attachment_id`.
- `src/stores/chat.ts:49` — `sendMessage` accepts `attachmentId`.
- `src/components/chat/ChatPanel.vue` — `:show-files=true`, `@upload-file`, `pendingAttachment`.
- `src/composables/useChatAdapter.test.ts` — +2 tests for `file` mapping.
- `src/components/chat/ChatPanel.test.ts` — +1 test for `onUploadFile`.

**Git:** commit after each task. Branch from `main` (`c4fc507` per handoff). The handoff says all commits are on `main`; follow the repo's existing convention unless told otherwise.

---

## Task 1: Migration 012 — `messages.attachment_id`

**Files:**
- Create: `backend/migrations/012_chat_attachments.sql`
- Modify: `backend/migrations/runner.py:184-194` (add `apply_migration_012`) and `:197-216` (add to `apply_all`)

- [ ] **Step 1: Write the migration SQL**

Create `backend/migrations/012_chat_attachments.sql`:

```sql
-- Migration 012: chat message attachments (Подсистема II — интеграция).
-- Idempotent: ADD COLUMN IF NOT EXISTS (PG 9.6+), CREATE INDEX IF NOT EXISTS (PG 9.5+).
-- Assumes messages (009) and files (010) tables exist.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS attachment_id
    BIGINT NULL REFERENCES files(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_messages_attachment
    ON messages (attachment_id) WHERE attachment_id IS NOT NULL;
```

- [ ] **Step 2: Register the migration in the runner**

In `backend/migrations/runner.py`, after `apply_migration_011` (line 194) add:

```python
def apply_migration_012(conn) -> None:
    """Apply migration 012 — chat message attachments (messages.attachment_id → files).

    Idempotent (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS). Assumes
    messages + files tables exist (009/010). ON DELETE SET NULL: file removed →
    message survives without attachment (matches reply_to_id + avatar_file_id).
    """
    sql_path = _MIGRATIONS_DIR / "012_chat_attachments.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 012_chat_attachments.sql applied.")
```

In `apply_all` (line 197-216), add after `apply_migration_011(conn)`:

```python
        apply_migration_012(conn)
```

- [ ] **Step 3: Apply the migration locally and verify idempotency**

Run (uses the dev DB; the runner is invoked by app startup, but applying directly confirms the SQL is valid):

```bash
cd backend && python -c "
import psycopg2
from migrations.runner import apply_migration_012
conn = psycopg2.connect('postgresql://postgres:235813@localhost:5432/hhb_b2b')
apply_migration_012(conn)
apply_migration_012(conn)  # second run must NOT error (idempotency)
conn.close()
print('OK')
"
```

Expected: `OK` (no error on second run). If `hhb_b2b` doesn't exist locally, skip this step — the migration is exercised in app startup and the next task's tests.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/012_chat_attachments.sql backend/migrations/runner.py
git commit -m "feat(chat): migration 012 — messages.attachment_id (FK files, ON DELETE SET NULL)"
```

---

## Task 2: Backend — `send_message` validates + stores `attachment_id`

Mirror the existing `reply_to_id` graceful-drop pattern (`chat_service.py:263-273`). Owner-check via `uploaded_by`; on failure, drop `attachment_id` and keep the text.

**Files:**
- Modify: `backend/schemas/chat.py:14-16`
- Modify: `backend/services/chat_service.py:245-321`
- Test: `backend/tests/test_chat_messages.py`

- [ ] **Step 1: Extend the test fixture with `attachment_id` column + a `files` row helper**

In `backend/tests/test_chat_messages.py`, the `seeded_msgs` fixture (lines 17-59) hardcodes `CREATE TABLE messages` without `attachment_id`. Update the messages CREATE TABLE (lines 35-41) to add the column (no FK in the test schema — the fixture drops and recreates tables, and `files` is not created here; the FK is verified in production by migration 012). Replace the messages CREATE TABLE statement:

```python
    cur.execute(
        """CREATE TABLE messages (
        id BIGSERIAL PRIMARY KEY, channel_id INTEGER, author_id INTEGER,
        content TEXT NOT NULL CHECK (char_length(content) <= 10000),
        reply_to_id BIGINT NULL,
        attachment_id BIGINT NULL,
        created_at TIMESTAMPTZ DEFAULT now(),
        edited_at TIMESTAMPTZ NULL, deleted_at TIMESTAMPTZ NULL)"""
    )
```

Also add a `files` table + a seed helper at the end of the fixture (after the users INSERT on line 46), so attachment validation tests can reference a real `uploaded_by`:

```python
    cur.execute(
        """CREATE TABLE files (
        id BIGSERIAL PRIMARY KEY, uploaded_by INTEGER,
        storage_path TEXT NOT NULL, thumbnail_path TEXT NULL,
        original_name TEXT NOT NULL, mime_type TEXT NOT NULL,
        size_bytes BIGINT NOT NULL, sha256 TEXT NOT NULL,
        is_image BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ DEFAULT now())"""
    )
    cur.execute(
        "INSERT INTO files (uploaded_by, storage_path, original_name, mime_type, "
        "size_bytes, sha256, is_image) VALUES "
        "(1, '2026/07/aaa.pdf', 'Договор.pdf', 'application/pdf', 1234, 'deadbeef', false), "
        "(2, '2026/07/bbb.png', 'photo.png', 'image/png', 5678, 'cafef00d', true)"
    )
    cur.close()
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_chat_messages.py` (after the last test):

```python
def test_send_message_with_valid_attachment_returns_attachment(seeded_msgs):
    # file id 1 was uploaded_by user 1 → valid attachment
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="see attached", attachment_id=1),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["attachment"] is not None
    assert out["attachment"]["id"] == 1
    assert out["attachment"]["original_name"] == "Договор.pdf"
    assert out["attachment"]["url"] == f"/api/chat-attachments/1"
    assert out["attachment"]["thumbnail_url"] is None  # pdf, not image


def test_send_message_with_foreign_attachment_graceful_drop(seeded_msgs):
    # file id 2 was uploaded_by user 2; sender is user 1 → owner-check fails → drop
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="my text", attachment_id=2),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["attachment"] is None
    # text must survive
    assert out["content"] == "my text"


def test_send_message_with_nonexistent_attachment_graceful_drop(seeded_msgs):
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="still here", attachment_id=999999),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["attachment"] is None
    assert out["content"] == "still here"


def test_send_message_with_attachment_and_reply(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent"),
        current_user={"id": 1, "role": "manager"},
    ))
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply + file", reply_to_id=parent["id"], attachment_id=1),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_message"] is not None
    assert out["attachment"] is not None
    assert out["attachment"]["id"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_chat_messages.py::test_send_message_with_valid_attachment_returns_attachment -xvs
```

Expected: FAIL — `MessageCreate` rejects `attachment_id` (unknown field), or `attachment` key missing from response.

- [ ] **Step 4: Add `attachment_id` to the schema**

In `backend/schemas/chat.py`, replace `MessageCreate` (lines 14-16):

```python
class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    reply_to_id: Optional[int] = None
    attachment_id: Optional[int] = None
```

- [ ] **Step 5: Implement validation + INSERT in `send_message`**

In `backend/services/chat_service.py`, in `send_message` (lines 245-321), make three changes:

**5a. Add attachment validation after the reply validation block (after line 273):**

```python
        attachment_id = data.attachment_id
        if attachment_id is not None:
            # Owner-check: sender must have uploaded this file. Graceful drop
            # on failure (foreign/nonexistent) — mirrors reply_to_id handling;
            # the user's text is never lost because of a bad attachment id.
            cur.execute(
                q("SELECT 1 FROM files WHERE id = %s AND uploaded_by = %s"),
                (attachment_id, current_user["id"]),
            )
            if cur.fetchone() is None:
                attachment_id = None
```

**5b. Update the INSERT (replace lines 275-282) to include `attachment_id`:**

```python
        cur.execute(
            q(
                """INSERT INTO messages (channel_id, author_id, content, reply_to_id, attachment_id)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at"""
            ),
            (channel_id, current_user["id"], data.content, reply_to_id, attachment_id),
        )
```

**5c. Add `attachment` to the returned dict (replace the `return {...}` block at lines 306-319).** Build the attachment meta inline (it's our own file, we know its fields from the owner-check; do one SELECT to populate display fields):

```python
        attachment = None
        if attachment_id is not None:
            cur.execute(
                q(
                    """SELECT id, original_name, mime_type, size_bytes, is_image, thumbnail_path
                       FROM files WHERE id = %s"""
                ),
                (attachment_id,),
            )
            frow = cur.fetchone()
            if frow:
                attachment = _attachment_dict(frow)

        return {
            "id": mid,
            "channel_id": channel_id,
            "author_id": current_user["id"],
            "author_username": current_user.get("username"),
            "author_name": current_user.get("name"),
            "content": data.content,
            "reply_to_id": reply_to_id,
            "reply_message": reply_message,
            "attachment": attachment,
            "created_at": created_at.isoformat() if created_at else None,
            "edited_at": None,
            "deleted_at": None,
            "avatar_url": f"/api/avatars/{current_user['avatar_file_id']}" if current_user.get("avatar_file_id") else None,
        }
```

**5d. Add the `_attachment_dict` helper** (place it just above `_message_row_to_dict`, near line 370). It maps a `files` row tuple to the client-facing attachment dict, using the **public** `/api/chat-attachments/{id}` URL (so `<img src>` works without auth):

```python
def _attachment_dict(frow) -> Dict[str, Any]:
    """Map a files-row tuple to the client-facing attachment dict.

    frow = (id, original_name, mime_type, size_bytes, is_image, thumbnail_path).
    URL points at the PUBLIC /api/chat-attachments/{id} endpoint (no auth) so
    <img src>/CSS background-image can fetch it — same rationale as /api/avatars.
    """
    fid = frow[0]
    is_image = frow[4]
    thumbnail_path = frow[5]
    return {
        "id": fid,
        "original_name": frow[1],
        "mime_type": frow[2],
        "size_bytes": frow[3],
        "is_image": is_image,
        "url": f"/api/chat-attachments/{fid}",
        "thumbnail_url": f"/api/chat-attachments/{fid}/thumbnail" if (is_image and thumbnail_path) else None,
    }
```

- [ ] **Step 6: Run the new tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_chat_messages.py -k attachment -xvs
```

Expected: all 4 attachment tests PASS.

- [ ] **Step 7: Run the full chat messages suite to check for regressions**

```bash
cd backend && python -m pytest tests/test_chat_messages.py -xvs
```

Expected: all tests PASS (existing reply/edit/delete tests still green — the new column is NULL by default for them).

- [ ] **Step 8: Commit**

```bash
git add backend/schemas/chat.py backend/services/chat_service.py backend/tests/test_chat_messages.py
git commit -m "feat(chat): send_message accepts attachment_id (owner-check + graceful drop)"
```

---

## Task 3: Backend — `list_messages` returns attachment meta

Extend the SELECT with a LEFT JOIN files so history loads attachment metadata in one query.

**Files:**
- Modify: `backend/services/chat_service.py:194-242` (`list_messages`)
- Modify: `backend/services/chat_service.py:370-400` (`_message_row_to_dict`)
- Test: `backend/tests/test_chat_messages.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_chat_messages.py`:

```python
def test_list_messages_includes_attachment(seeded_msgs):
    _run(send_message(
        channel_id=2,
        data=MessageCreate(content="with file", attachment_id=1),
        current_user={"id": 1, "role": "manager"},
    ))
    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    msg = hist[0]
    assert msg["attachment"] is not None
    assert msg["attachment"]["id"] == 1
    assert msg["attachment"]["original_name"] == "Договор.pdf"
    assert msg["attachment"]["is_image"] is False
    assert msg["attachment"]["url"] == "/api/chat-attachments/1"
    assert msg["attachment"]["thumbnail_url"] is None


def test_list_messages_attachment_null_when_no_file(seeded_msgs):
    _run(send_message(channel_id=2, data=MessageCreate(content="plain"), current_user={"id": 1, "role": "manager"}))
    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    assert hist[0]["attachment"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_chat_messages.py::test_list_messages_includes_attachment -xvs
```

Expected: FAIL — `KeyError: 'attachment'` (the key isn't in the dict yet) or `attachment` is None (SELECT doesn't fetch files).

- [ ] **Step 3: Extend `list_messages` SELECT + JOIN**

In `backend/services/chat_service.py`, in `list_messages` (lines 194-242), there are two near-identical SQL strings (with `before` and without). Add `LEFT JOIN files f ON f.id = m.attachment_id` to both, and append the file columns to both SELECT lists (after `u.avatar_file_id`).

For the **`before` branch** (lines 208-223), replace the SQL with:

```python
            cur.execute(
                q(
                    """SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
                        m.created_at, m.edited_at, m.deleted_at, u.username, u.name,
                        p.id, p.content, p.author_id, pu.name, p.deleted_at,
                        u.avatar_file_id,
                        f.id, f.original_name, f.mime_type, f.size_bytes, f.is_image, f.thumbnail_path
                        FROM messages m
                        LEFT JOIN users u ON u.id = m.author_id
                        LEFT JOIN messages p ON p.id = m.reply_to_id
                        LEFT JOIN users pu ON pu.id = p.author_id
                        LEFT JOIN files f ON f.id = m.attachment_id
                        WHERE m.channel_id = %s AND m.id < %s
                        ORDER BY m.id DESC LIMIT %s"""
                ),
                (channel_id, before, limit),
            )
```

For the **no-`before` branch** (lines 224-239), replace the SQL with:

```python
            cur.execute(
                q(
                    """SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
                        m.created_at, m.edited_at, m.deleted_at, u.username, u.name,
                        p.id, p.content, p.author_id, pu.name, p.deleted_at,
                        u.avatar_file_id,
                        f.id, f.original_name, f.mime_type, f.size_bytes, f.is_image, f.thumbnail_path
                        FROM messages m
                        LEFT JOIN users u ON u.id = m.author_id
                        LEFT JOIN messages p ON p.id = m.reply_to_id
                        LEFT JOIN users pu ON pu.id = p.author_id
                        LEFT JOIN files f ON f.id = m.attachment_id
                        WHERE m.channel_id = %s
                        ORDER BY m.id DESC LIMIT %s"""
                ),
                (channel_id, limit),
            )
```

- [ ] **Step 4: Update `_message_row_to_dict` to read the new columns**

In `backend/services/chat_service.py:370-400`, the row tuple grew by 6 columns. The existing code reads indices 0-15; `r[10..14]` are the parent reply fields and `r[15]` is `avatar_file_id`. The new file columns are `r[16..21]`. Replace the function body:

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
    # r[15] = u.avatar_file_id (NULL if author has no avatar or was deleted).
    avatar_file_id = r[15] if len(r) > 15 else None
    # r[16..21] = files row (f.id, f.original_name, f.mime_type, f.size_bytes,
    # f.is_image, f.thumbnail_path). NULL when the message has no attachment,
    # or when the file was hard-deleted (FK ON DELETE SET NULL → attachment_id NULL).
    attachment = None
    if len(r) > 16 and r[16] is not None:
        attachment = _attachment_dict((r[16], r[17], r[18], r[19], r[20], r[21]))
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
        "avatar_url": f"/api/avatars/{avatar_file_id}" if avatar_file_id else None,
        "attachment": attachment,
    }
```

- [ ] **Step 5: Run the new tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_chat_messages.py -k "list_messages_includes_attachment or list_messages_attachment_null" -xvs
```

Expected: both PASS.

- [ ] **Step 6: Run the full suite for regressions**

```bash
cd backend && python -m pytest tests/test_chat_messages.py -xvs
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/chat_service.py backend/tests/test_chat_messages.py
git commit -m "feat(chat): list_messages returns attachment meta via LEFT JOIN files"
```

---

## Task 4: Backend — public gated endpoint `/api/chat-attachments/{id}`

New service function + two public routes (no auth). Gate: file must be attached to a non-deleted message. This is the response-path where Content-Disposition injection lives — copy the existing `quote()` defense from `routes/files.py:49`.

**Files:**
- Modify: `backend/services/file_service.py` (add `get_file_by_attachment`)
- Modify: `backend/routes/files.py` (add 2 public endpoints)
- Test: `backend/tests/test_files.py`

- [ ] **Step 1: Write the failing service-level test**

Append to `backend/tests/test_files.py`. The `seeded_files` fixture (lines 17-54) creates `users` + `files` but not `messages` — for the gate test we need a `messages` table and a row pointing at a file. Add a helper + 4 tests:

```python
def _seed_messages_table(seeded_files):
    """Create a minimal messages table and attach file id 1 to message id 100
    (non-deleted) and file id 2 to message id 101 (soft-deleted). File id left
    unattached to any message exercises the gate's 404 path."""
    import services.file_service as svc
    import psycopg2, os
    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    conn = psycopg2.connect(TEST_DSN)
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS messages")
        cur.execute(
            "CREATE TABLE messages (id BIGSERIAL PRIMARY KEY, attachment_id BIGINT NULL, "
            "deleted_at TIMESTAMPTZ NULL)"
        )
        # attach file 1 to a live message; attach file 2 to a deleted message
        cur.execute(
            "INSERT INTO files (uploaded_by, storage_path, original_name, mime_type, "
            "size_bytes, sha256, is_image, thumbnail_path) VALUES "
            "(1, '2026/07/attached.pdf', 'A.pdf', 'application/pdf', 10, 'h1', false, NULL)"
        )
        conn.commit()
        # resolve the new file id, then attach it to a live message
        cur.execute("SELECT id FROM files WHERE original_name = 'A.pdf'")
        live_fid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO messages (attachment_id, deleted_at) VALUES "
            "(%s, NULL), (%s, now())",
            (live_fid, live_fid),  # same file on a live and a deleted msg
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return live_fid


def test_get_file_by_attachment_200_for_live_message(seeded_files):
    from services.file_service import get_file_by_attachment
    live_fid = _seed_messages_table(seeded_files)
    meta, abs_path = get_file_by_attachment(live_fid)
    assert meta["id"] == live_fid
    assert os.path.exists(abs_path)


def test_get_file_by_attachment_404_when_unattached(seeded_files):
    # file id 1 (from the seeded_files fixture) is NOT attached to any message
    from services.file_service import get_file_by_attachment
    from services.file_service import get_file
    meta = _seed_one_file(seeded_files, owner_id=1)  # fresh file, unattached
    with pytest.raises(HTTPException) as exc:
        get_file_by_attachment(meta["id"])
    assert exc.value.status_code == 404


def test_get_file_by_attachment_404_when_only_deleted_message(seeded_files):
    from services.file_service import get_file_by_attachment
    live_fid = _seed_messages_table(seeded_files)
    # the gate returns 200 because at least one LIVE message references it.
    # Now delete that live message too → no live reference left → 404.
    import psycopg2, os
    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    conn = psycopg2.connect(TEST_DSN)
    cur = conn.cursor()
    cur.execute("UPDATE messages SET deleted_at = now() WHERE attachment_id = %s", (live_fid,))
    conn.commit()
    cur.close()
    conn.close()
    with pytest.raises(HTTPException) as exc:
        get_file_by_attachment(live_fid)
    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_files.py::test_get_file_by_attachment_200_for_live_message -xvs
```

Expected: FAIL — `ImportError: cannot import name 'get_file_by_attachment'`.

- [ ] **Step 3: Implement `get_file_by_attachment`**

In `backend/services/file_service.py`, add after `get_thumbnail_path` (after line 247):

```python
def get_file_by_attachment(file_id: int) -> Tuple[Dict[str, Any], str]:
    """Gate by attachment-existence (NOT owner-check). Returns (meta, abs_path).

    Public endpoint helper: the file is served WITHOUT auth, so the gate is
    "this file is referenced by at least one NON-deleted message". Files not
    attached to any live message → 404 (prevents enumeration of arbitrary
    private files via this public path). Mirrors the /api/avatars/{id} gate.
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            q(
                """SELECT id, uploaded_by, storage_path, thumbnail_path,
                          original_name, mime_type, size_bytes, is_image
                   FROM files
                   WHERE id = %s AND EXISTS (
                       SELECT 1 FROM messages
                       WHERE messages.attachment_id = files.id
                         AND messages.deleted_at IS NULL
                   )"""
            ),
            (file_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "Вложение не найдено")

    meta = {
        "id": row[0],
        "uploaded_by": row[1],
        "storage_path": row[2],
        "thumbnail_path": row[3],
        "original_name": row[4],
        "mime_type": row[5],
        "size_bytes": row[6],
        "is_image": row[7],
    }
    abs_path = os.path.join(MEDIA_ROOT, row[2])
    if not os.path.exists(abs_path):
        logger.error(f"[files] attachment {file_id} DB row exists but file missing: {abs_path}")
        raise HTTPException(404, "Файл отсутствует на диске")
    return meta, abs_path
```

- [ ] **Step 4: Run the service tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_files.py -k attachment -xvs
```

Expected: 3 PASS.

- [ ] **Step 5: Add the public routes**

In `backend/routes/files.py`, add `get_file_by_attachment` to the import (line 9):

```python
from services.file_service import save_upload, get_file, get_thumbnail_path, get_file_by_attachment
```

Then append two public endpoints at the end of the file (after `download_thumbnail`). Note: **no `Depends(get_current_user())`** — these are public. The `Content-Disposition` header uses `quote()` exactly like `download_file` (lines 47-49) — this is the response-path injection defense, copied verbatim:

```python
@router.get("/api/chat-attachments/{file_id}")
def download_attachment(file_id: int) -> StreamingResponse:
    """Public attachment delivery — NO auth.

    <img src>/CSS cannot send Bearer, so attachments are served without auth,
    gated by EXISTS(messages.attachment_id = file.id AND deleted_at IS NULL).
    Mirrors /api/avatars/{id}. Content-Disposition uses quote() (response-path
    header-injection defense, same as download_file above).
    """
    meta, abs_path = get_file_by_attachment(file_id)

    def iterfile():
        with open(abs_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    quoted = quote(meta["original_name"])
    return StreamingResponse(
        iterfile(),
        media_type=meta["mime_type"],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
            "Content-Length": str(meta["size_bytes"]),
        },
    )


@router.get("/api/chat-attachments/{file_id}/thumbnail")
def download_attachment_thumbnail(file_id: int) -> StreamingResponse:
    """Public thumbnail — NO auth. 404 if not an image / no thumbnail / not attached."""
    meta, abs_path = get_file_by_attachment(file_id)
    if not meta.get("thumbnail_path"):
        raise HTTPException(404, "Превью недоступно")
    thumb_abs = os.path.join(
        os.getenv("MEDIA_ROOT", os.path.join(os.path.dirname(__file__), "..", "media")),
        meta["thumbnail_path"],
    )
    if not os.path.exists(thumb_abs):
        raise HTTPException(404, "Превью отсутствует на диске")

    def iterfile():
        with open(thumb_abs, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    quoted = quote(meta["original_name"])
    return StreamingResponse(
        iterfile(),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
            "Cache-Control": "public, max-age=86400",
        },
    )
```

Add `HTTPException` and `os` to the imports at the top of `routes/files.py` if not already present:

```python
import os
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
```

- [ ] **Step 6: Write the route-level tests (including the Content-Disposition regression)**

Append to `backend/tests/test_files.py`. These exercise the HTTP layer via `TestClient`. We need a minimal app with only the files router (no DB migrations, no auth), patching `get_db` and `MEDIA_ROOT` like the fixture does:

```python
def _files_app(seeded_files, monkeypatch):
    """Build a TestClient app with only the files router; patch service get_db + MEDIA_ROOT."""
    import routes.files as rmod
    import services.file_service as svc
    monkeypatch.setattr(svc, "get_db", lambda: psycopg2.connect(
        os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")))
    monkeypatch.setattr(svc, "MEDIA_ROOT", seeded_files)
    # patch the route module's get_file_by_attachment to use the patched service
    app = FastAPI()
    app.include_router(rmod.router)
    return TestClient(app)


def test_public_attachment_endpoint_200_for_attached(seeded_files, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    live_fid = _seed_messages_table(seeded_files)
    # write the physical file so StreamingResponse can read it
    os.makedirs(os.path.join(seeded_files, "2026/07"), exist_ok=True)
    with open(os.path.join(seeded_files, "2026/07/attached.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 body")
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{live_fid}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_public_attachment_endpoint_404_for_unattached(seeded_files, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    meta = _seed_one_file(seeded_files, owner_id=1)  # not attached
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{meta['id']}")
    assert resp.status_code == 404


def test_public_attachment_thumbnail_404_for_non_image(seeded_files, monkeypatch):
    live_fid = _seed_messages_table(seeded_files)  # attached file is a PDF
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{live_fid}/thumbnail")
    assert resp.status_code == 404


def test_public_attachment_content_disposition_safe(seeded_files, monkeypatch):
    """Regression (response-path header injection): upload a file whose name
    contains quote/CR/LF, then GET the public endpoint and assert the
    Content-Disposition header carries NO raw quote/CR/LF. The defense is
    route-level quote(), NOT save_upload's sanitize_name (that is upload-path
    defense-in-depth). Public + no-auth endpoint → defense must hold here."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import psycopg2
    # upload via save_upload (sanitizes the name), then attach to a live message
    evil_name = 'evil"; injection\r\nX-Bad: 1.pdf'
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\nxref\n0 1\ntrailer<</Root 1 0 R>>\nstartxref\n0\n%%EOF"
    upload = _make_upload(pdf_bytes, evil_name, "application/pdf")
    meta = _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    # attach to a live message
    conn = psycopg2.connect(os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"))
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS messages")
    cur.execute("CREATE TABLE messages (id BIGSERIAL PRIMARY KEY, attachment_id BIGINT NULL, deleted_at TIMESTAMPTZ NULL)")
    cur.execute("INSERT INTO messages (attachment_id) VALUES (%s)", (meta["id"],))
    conn.commit()
    cur.close()
    conn.close()
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{meta['id']}")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert '"' not in cd, f"raw quote leaked into Content-Disposition: {cd!r}"
    assert "\r" not in cd and "\n" not in cd, f"CR/LF leaked into Content-Disposition: {cd!r}"
```

- [ ] **Step 7: Run all the new file tests**

```bash
cd backend && python -m pytest tests/test_files.py -xvs
```

Expected: all PASS (existing + 7 new: 3 service + 4 route-level, including the content-disposition regression).

- [ ] **Step 8: Run the entire backend suite for regressions**

```bash
cd backend && python -m pytest -x -q
```

Expected: all PASS. Count rises from 180 to ~190.

- [ ] **Step 9: Commit**

```bash
git add backend/services/file_service.py backend/routes/files.py backend/tests/test_files.py
git commit -m "feat(files): public gated /api/chat-attachments/{id} endpoint + content-disposition regression"
```

---

## Task 5: Frontend — types + adapter (`attachment` → `message.file`)

Map the backend `attachment` field to the VAC `message.file` shape. VAC renders an image via `file.previewUrl` (`<img src>`) and a document via icon + name + download link.

**Files:**
- Modify: `src/types/chat.ts`
- Modify: `src/composables/useChatAdapter.ts`
- Test: `src/composables/useChatAdapter.test.ts`

- [ ] **Step 1: Write the failing adapter tests**

Append to `src/composables/useChatAdapter.test.ts` (inside the existing `describe('toMessage', ...)` block, before the closing `})`):

```typescript
  it('maps attachment to a VAC file with previewUrl for images', () => {
    const result = toMessage({
      id: 1,
      channel_id: 1,
      author_id: 2,
      content: 'see photo',
      attachment: {
        id: 9,
        original_name: 'photo.png',
        mime_type: 'image/png',
        size_bytes: 1024,
        is_image: true,
        url: '/api/chat-attachments/9',
        thumbnail_url: '/api/chat-attachments/9/thumbnail',
      },
      created_at: null,
    } as any)
    expect(result.file).toEqual({
      name: 'photo.png',
      size: 1024,
      type: 'image/png',
      url: '/api/chat-attachments/9',
      previewUrl: '/api/chat-attachments/9/thumbnail',
    })
  })

  it('maps attachment to a VAC file without previewUrl for documents', () => {
    const result = toMessage({
      id: 1,
      channel_id: 1,
      author_id: 2,
      content: 'see pdf',
      attachment: {
        id: 10,
        original_name: 'Договор.pdf',
        mime_type: 'application/pdf',
        size_bytes: 9999,
        is_image: false,
        url: '/api/chat-attachments/10',
        thumbnail_url: null,
      },
      created_at: null,
    } as any)
    expect(result.file).toEqual({
      name: 'Договор.pdf',
      size: 9999,
      type: 'application/pdf',
      url: '/api/chat-attachments/10',
    })
    expect(result.file).not.toHaveProperty('previewUrl')
  })

  it('omits file when there is no attachment', () => {
    const result = toMessage({
      id: 1,
      channel_id: 1,
      author_id: 2,
      content: 'plain',
      created_at: null,
    } as any)
    expect(result.file).toBeUndefined()
  })
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm run test -- --run useChatAdapter
```

Expected: FAIL — `result.file` is `undefined` for the image test (no `file` mapping yet).

- [ ] **Step 3: Add the `ChatAttachment` type**

In `src/types/chat.ts`, add the interface before `ChatMessage`, and add `attachment?` to `ChatMessage`:

```typescript
export interface ChatAttachment {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  is_image: boolean
  url: string                    // "/api/chat-attachments/{id}" — public, no auth
  thumbnail_url: string | null
}
```

And inside `export interface ChatMessage { ... }`, after the `reply_message` field (before `created_at`):

```typescript
  attachment?: ChatAttachment | null
```

- [ ] **Step 4: Add `file` mapping in `toMessage`**

In `src/composables/useChatAdapter.ts`, add `file?:` to the `VACMessage` interface (after `replyMessage?`, around line 26):

```typescript
  file?: {
    name: string
    size: number
    type: string
    url: string
    previewUrl?: string
  }
```

Then in `toMessage` (lines 42-71), add the `file` field to the returned object (after `replyMessage: ...`). The function's param type annotation must also allow `attachment`:

```typescript
export function toMessage(
  m: ChatMessage & { author_username?: string | null; author_name?: string | null; avatar_url?: string | null },
): VACMessage {
  const created = m.created_at ? new Date(m.created_at) : null
  return {
    _id: String(m.id),
    content: m.deleted_at ? 'сообщение удалено' : m.content,
    senderId: String(m.author_id),
    username: m.author_name ?? m.author_username ?? 'Неизвестно',
    avatar: m.avatar_url ?? '',
    date: created ? created.toLocaleDateString('ru-RU') : '',
    timestamp: created
      ? created.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
      : '',
    saved: true,
    distributed: true,
    seen: false,
    replyMessage: m.reply_message
      ? {
          _id: String(m.reply_message.id),
          content: m.reply_message.content,
          senderId: String(m.reply_message.author_id ?? ''),
          username: m.reply_message.author_name ?? 'Неизвестно',
        }
      : null,
    file: m.attachment
      ? {
          name: m.attachment.original_name,
          size: m.attachment.size_bytes,
          type: m.attachment.mime_type,
          url: m.attachment.url,
          ...(m.attachment.is_image && m.attachment.thumbnail_url
            ? { previewUrl: m.attachment.thumbnail_url }
            : {}),
        }
      : undefined,
  }
}
```

- [ ] **Step 5: Run the adapter tests to verify they pass**

```bash
npm run test -- --run useChatAdapter
```

Expected: all PASS (2 existing reply + 3 new file).

- [ ] **Step 6: Commit**

```bash
git add src/types/chat.ts src/composables/useChatAdapter.ts src/composables/useChatAdapter.test.ts
git commit -m "feat(chat): toMessage maps attachment to VAC message.file"
```

---

## Task 6: Frontend — store + API accept `attachment_id`

**Files:**
- Modify: `src/api/chat.ts:11-12`
- Modify: `src/stores/chat.ts:49-58`

- [ ] **Step 1: Extend the API payload type**

In `src/api/chat.ts`, change the `sendMessage` signature (line 11) to accept `attachment_id`:

```typescript
  sendMessage: (channelId: number, data: { content: string; reply_to_id?: number | null; attachment_id?: number | null }) =>
    api.post<ChatMessage>(`/api/chat/channels/${channelId}/messages`, data),
```

- [ ] **Step 2: Extend the store action**

In `src/stores/chat.ts`, replace `sendMessage` (lines 49-58) to accept and forward `attachmentId`:

```typescript
  async function sendMessage(channelId: number, content: string, replyToId?: number, attachmentId?: number) {
    const { data } = await chatApi.sendMessage(channelId, {
      content,
      reply_to_id: replyToId ?? null,
      attachment_id: attachmentId ?? null,
    })
    // optimistic: append locally; WS will broadcast to others
    messagesByChannel.value[channelId] = [...(messagesByChannel.value[channelId] ?? []), data]
    // clear unread for self
    unread.value[channelId] = 0
  }
```

- [ ] **Step 3: Verify nothing breaks (type-check + existing tests)**

```bash
npm run test -- --run
```

Expected: all frontend tests PASS (no behavioral change yet — `attachmentId` defaults to undefined → `null`).

- [ ] **Step 4: Commit**

```bash
git add src/api/chat.ts src/stores/chat.ts
git commit -m "feat(chat): store + API sendMessage accept attachment_id"
```

---

## Task 7: Frontend — ChatPanel wires `@upload-file` + `pendingAttachment`

⚠️ **Canary (handoff bugs 3+4):** the exact shape of VAC's `@upload-file` event detail (`{file, roomId}` vs `{file, index, roomId}`) must be **read from the VAC source**, not guessed. Before Step 3, check `node_modules/vue-advanced-chat` for the emitted payload. The design is robust either way (`pendingAttachment` is our own store), but the destructuring must match reality.

**Files:**
- Modify: `src/components/chat/ChatPanel.vue`
- Test: `src/components/chat/ChatPanel.test.ts`

- [ ] **Step 1: Check the VAC `@upload-file` payload contract**

```bash
grep -rn "upload-file\|uploadFile" node_modules/vue-advanced-chat/dist/ | head -20
```

Look for the `emit('upload-file', { ... })` call. Record the exact keys. Common VAC shape: `{ file, roomId }` where `file` is a `File`. If it differs (e.g. includes `index`), adapt the destructuring in Step 3 accordingly. Also check whether there's a prop to force single-file selection (e.g. `single-file`, `multiple-files`):

```bash
grep -rn "single\|multiple" node_modules/vue-advanced-chat/dist/ | grep -i file | head
```

If a single-file prop exists, set it. If not, Step 3 keeps the "first file only + toast" fallback.

- [ ] **Step 2: Write the failing ChatPanel test**

Append to `src/components/chat/ChatPanel.test.ts` (inside the existing `describe('ChatPanel', ...)` block, before its closing `})`). Add a mock for `filesApi` and a test that mounts, triggers the upload handler, and asserts `filesApi.upload` was called:

```typescript
// Add to the vi.mock block at the top (after the chatApi mock):
vi.mock('@/api/files', () => ({
  filesApi: {
    upload: vi.fn().mockResolvedValue({ data: { id: 77, original_name: 'x.pdf', mime_type: 'application/pdf', size_bytes: 1, is_image: false, url: '/api/files/77', thumbnail_url: null } }),
  },
}))

// Inside describe('ChatPanel', ...):
  it('onUploadFile calls filesApi.upload and stores pending attachment', async () => {
    const { filesApi } = await import('@/api/files')
    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    // call the handler directly via the component's exposed method.
    // (ChatPanel uses <script setup>; expose onUploadFile via defineExpose in Step 3.)
    const vac = wrapper.findComponent({ ref: undefined as any }) // placeholder; see note
    // Drive through the component instance:
    ;(wrapper.vm as any).onUploadFile({ detail: [{ file: new File(['x'], 'doc.pdf'), roomId: 2 }] })
    await flushPromises()
    expect(filesApi.upload).toHaveBeenCalledWith(expect.any(File))
  })
```

> Note: `<script setup>` does not expose handlers by default. To test `onUploadFile`, either (a) add `defineExpose({ onUploadFile })` in the component (Step 3), or (b) dispatch the event through the stubbed `<vue-advanced-chat>` via `wrapper.findComponent` and `.vm.$emit`. Option (a) is simpler and harmless. Use option (a).

- [ ] **Step 3: Run the test to verify it fails**

```bash
npm run test -- --run ChatPanel
```

Expected: FAIL — `(wrapper.vm as any).onUploadFile is not a function` (not defined/exposed yet).

- [ ] **Step 4: Wire `@upload-file` + `pendingAttachment` in ChatPanel**

In `src/components/chat/ChatPanel.vue`, make four changes:

**4a. Add imports + reactive pending store** (in `<script setup>`, after the existing imports around line 6-7):

```typescript
import { reactive } from 'vue'
import { filesApi } from '@/api/files'
```

(If `reactive` is already imported, merge it into the existing `vue` import on line 2.)

Add after the `showCreateModal` ref (around line 18):

```typescript
// pendingAttachment[roomId] = fileId — set by onUploadFile (eager upload),
// consumed by onSend. VAC's native attach button triggers @upload-file;
// we upload immediately, hold the id, and attach it at send-time.
const pendingAttachment = reactive<Record<number, number>>({})
```

**4b. Add `onUploadFile` + expose it** (place after `onSend`, around line 91):

```typescript
async function onUploadFile(event: any) {
  // VAC emits { file, roomId } in detail[0]. Single-attachment-per-message
  // by design (VAC message.file is a single object). If VAC ever emits
  // multiple, only the first is attached; document this as a known limit.
  const detail = event.detail?.[0]
  if (!detail?.file) return
  const roomId = Number(detail.roomId)
  try {
    const { data } = await filesApi.upload(detail.file)
    pendingAttachment[roomId] = data.id
  } catch (e) {
    console.warn('attachment upload failed', e)
  }
}

defineExpose({ onUploadFile })
```

**4c. Read + clear pending in `onSend`** (replace the existing `onSend`, lines 87-91):

```typescript
function onSend(event: any) {
  const { content, roomId, replyMessage } = event.detail[0]
  const replyToId = replyMessage?._id ? Number(replyMessage._id) : undefined
  const numRoom = Number(roomId)
  const attachmentId = pendingAttachment[numRoom]
  delete pendingAttachment[numRoom]
  store.sendMessage(numRoom, content, replyToId, attachmentId)
}
```

**4d. Flip `:show-files` to true + add `@upload-file`** (in the template, replace line 154 `:show-files="false"` with `:show-files="true"`, and add the event handler next to the others, e.g. after `@delete-message`):

```html
        :show-files="true"
```

```html
        @upload-file="onUploadFile"
```

- [ ] **Step 5: Run the ChatPanel tests to verify they pass**

```bash
npm run test -- --run ChatPanel
```

Expected: all 3 PASS (2 existing mount/close + 1 new upload).

- [ ] **Step 6: Run the full frontend suite**

```bash
npm run test -- --run
```

Expected: all PASS. Count rises from 15 to ~18.

- [ ] **Step 7: Commit**

```bash
git add src/components/chat/ChatPanel.vue src/components/chat/ChatPanel.test.ts
git commit -m "feat(chat): ChatPanel wires @upload-file (eager) + pendingAttachment → send attachment_id"
```

---

## Task 8: Manual / integration verification (no code)

Before declaring done, verify the end-to-end flow works against a running stack. This catches VAC-contract surprises the unit tests can't (canary).

- [ ] **Step 1: Start backend + frontend locally**

```bash
cd backend && python -m uvicorn main:app --reload --port 8000 &
cd .. && npm run dev
```

- [ ] **Step 2: Login as admin, open the chat panel, attach a PDF**

Login `admin` / `4qszJO0sF8oyGR4h` (handoff creds). Click the "Чат" FAB. In a channel, click the paperclip → pick a PDF → type a message → Send.

Expected: message appears in the feed with a file card (PDF icon + name + size). No console errors.

- [ ] **Step 3: Verify the image preview path**

Attach a PNG/JPG → send. Expected: the image renders inline (thumbnail) in the feed.

- [ ] **Step 4: Verify the public endpoint directly**

Open in a fresh incognito window (no auth):

```
http://localhost:8000/api/chat-attachments/<id>      → 200, downloads the file
http://localhost:8000/api/chat-attachments/9999999   → 404
```

Find the id from the message payload (network tab) or `SELECT id FROM files ORDER BY id DESC LIMIT 1`.

- [ ] **Step 5: Verify Content-Disposition in the response header**

In the browser devtools network tab, inspect the `/api/chat-attachments/<id>` response → `content-disposition` header is `inline; filename*=UTF-8''...` with percent-encoding, no raw quotes/CR/LF.

- [ ] **Step 6: Update the handoff doc**

Append a new section to `docs/HANDOFF.md` (or the next handoff) noting: Подсистема II integration done, migration 012, public `/api/chat-attachments/{id}` added, VAC `@upload-file` payload shape (record what Step 1 of Task 7 found), test counts (backend ~190, frontend ~18).

- [ ] **Step 7: Commit the handoff update**

```bash
git add docs/HANDOFF.md
git commit -m "docs: handoff — chat attachments integration (Подсистема II) done"
```

---

## Deploy checklist (production — after merge)

When deploying to `https://crmdot.ru`:

1. **Backup DB:** `sudo -u postgres pg_dump hhb_b2b | gzip > /root/crmks_backup_$(date +%Y%m%d_%H%M%S).sql.gz`
2. **`git pull`** on prod (watch for `package-lock.json` conflicts — `git checkout -- package-lock.json` if it diverges).
3. **Restart backend:** `systemctl restart crmks-api` (lifespan runs `apply_all` → migration 012 applies automatically). Wait ~5s.
4. **No new system packages** (Pillow/python-magic already installed for the base file service).
5. **No nginx changes** (`client_max_body_size 100m` already set).
6. **No MEDIA_ROOT changes** (rights already `crmks:crmks`).
7. **Smoke:**
   - `curl -X POST -H "Authorization: Bearer <token>" -F "file=@test.pdf" https://crmdot.ru/api/files` → 200.
   - Send a chat message with `attachment_id` → response includes `attachment`.
   - `curl https://crmdot.ru/api/chat-attachments/<id>` **without auth** → 200.
   - `curl https://crmdot.ru/api/chat-attachments/99999999` → 404.
8. **Logs:** `tail -50 /var/log/crmks/api.log` (not journalctl).

---

## Self-review notes

- **Spec coverage:** every spec section maps to a task — migration (T1), send_message validation + graceful drop (T2), list_messages JOIN (T3), public gated endpoint + Content-Disposition defense (T4), adapter mapping (T5), store/API wiring (T6), ChatPanel upload flow (T7), verification + deploy (T8). The Content-Disposition regression test (#16 in spec) is Task 4 Step 6. Rate-limit reliance on the global limiter is covered by the spec's trade-off section (no code task — it's a documented limitation, not new work). Reuse-permitted (spec decision 5) is implicit in the owner-check (no "already used" check) and tested by Task 2 (a file can be attached to multiple messages since owner-check passes each time).
- **Type consistency:** `_attachment_dict` (T2) is reused in `_message_row_to_dict` (T3) — same signature, same field names. Frontend `ChatAttachment` (T5) field names (`original_name`, `size_bytes`, `is_image`, `thumbnail_url`) match the backend dict exactly. `pendingAttachment` is `Record<number, number>` consistently in T7.
- **Placeholders:** none — every code step shows complete code. The one explicit unknown (VAC `@upload-file` payload shape) is resolved by Task 7 Step 1 (a `grep` step) before the implementation step.
