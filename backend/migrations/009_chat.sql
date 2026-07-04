-- Migration 009: chat subsystem (channels, channel_members, messages, read_state).
-- Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guards).
-- Assumes users table already exists (created by startup/db_init).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'channels'
    ) THEN
        CREATE TABLE channels (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            type            TEXT NOT NULL CHECK (type IN ('general','department','topic')),
            department_role TEXT NULL,
            created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            archived        BOOLEAN NOT NULL DEFAULT false
        );
        CREATE INDEX idx_channels_type ON channels (type);
        -- department: одна роль = один канал
        CREATE UNIQUE INDEX idx_channels_department_role_unique
            ON channels (department_role) WHERE type = 'department';
        -- general: ровно один (partial index по id не мешает NULL department_role)
        CREATE UNIQUE INDEX idx_channels_general_unique
            ON channels (id) WHERE type = 'general';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'channel_members'
    ) THEN
        CREATE TABLE channel_members (
            channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (channel_id, user_id)
        );
        CREATE INDEX idx_channel_members_user ON channel_members (user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'messages'
    ) THEN
        CREATE TABLE messages (
            -- BIGSERIAL: chat is high-volume; avoid wraparound past ~2.1B messages
            id          BIGSERIAL PRIMARY KEY,
            channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            -- nullable so ON DELETE SET NULL can succeed when a referenced user is deleted
            author_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            content     TEXT NOT NULL CHECK (char_length(content) <= 10000), -- 10000 char cap matches MessageCreate.max_length in schemas/chat.py; prevents giant pastes flooding WS fan-out
            reply_to_id BIGINT NULL REFERENCES messages(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            edited_at   TIMESTAMPTZ NULL,
            deleted_at  TIMESTAMPTZ NULL
        );
        -- (channel_id, id DESC) aligns with list_messages cursor pagination (ORDER BY id DESC)
        CREATE INDEX idx_messages_channel_created
            ON messages (channel_id, id DESC);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'read_state'
    ) THEN
        CREATE TABLE read_state (
            user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel_id           INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            last_read_message_id BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, channel_id)
        );
    END IF;
END $$;

-- Засев general-канала (идемпотентный — partial UNIQUE index защищает от дубля)
INSERT INTO channels (name, type)
SELECT 'Общий чат', 'general'
WHERE NOT EXISTS (SELECT 1 FROM channels WHERE type = 'general');
