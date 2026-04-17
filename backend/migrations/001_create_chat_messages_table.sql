-- migrations/001_create_chat_messages_table.sql
-- ─────────────────────────────────────────────
-- Persistent chat history for analytics and platform optimisation.
--
-- Run once before deploying:
--   psql -d your_db -f migrations/001_create_chat_messages_table.sql
--
-- IMPORTANT: The FK to users(email) requires that your users table
-- uses email as a primary/unique key. If your users table uses a
-- different column, adjust or remove the FK constraint.

CREATE TABLE IF NOT EXISTS chat_messages (
    id               SERIAL        PRIMARY KEY,
    user_id          VARCHAR(100)  NOT NULL,
    session_id       VARCHAR(100)  NOT NULL,
    timestamp        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    -- The raw user question
    question         TEXT          NOT NULL,

    -- Generated SQL (NULL for greeting/chitchat turns)
    sql              TEXT,

    -- Conversational response shown to the user
    response         TEXT          NOT NULL,

    -- Serialised query results (JSON array of row objects)
    -- Kept for future replay/debugging; may be NULL for non-data turns
    results_json     TEXT,
    result_count     INTEGER       NOT NULL DEFAULT 0,

    -- AI metadata
    model_used       VARCHAR(100),
    confidence       VARCHAR(20),
    execution_ms     INTEGER       NOT NULL DEFAULT 0,

    -- Error message from DB execution, if any
    error            TEXT,

    -- Department scope
    department_code  VARCHAR(20),

    -- Intent classification result
    -- Values: greeting | chitchat | data_query | clarify_day | clarify_reply | unsafe
    intent           VARCHAR(50),

    -- JSON array of schema validation errors caught before DB execution
    -- e.g. ["column 'day_of_week' does not exist on faculty"]
    -- Useful for identifying systematic model mistakes
    validation_errors JSONB,

    -- User feedback on assistant response: +1 (thumbs up), -1 (thumbs down)
    feedback_score   SMALLINT,
    feedback_at      TIMESTAMPTZ
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
-- Core lookup: all messages for a user's session
CREATE INDEX IF NOT EXISTS idx_chat_user_session
    ON chat_messages (user_id, session_id);

-- Recent history per user
CREATE INDEX IF NOT EXISTS idx_chat_user_timestamp
    ON chat_messages (user_id, timestamp DESC);

-- Per-department analytics
CREATE INDEX IF NOT EXISTS idx_chat_department
    ON chat_messages (department_code, timestamp DESC);

-- Failure analysis
CREATE INDEX IF NOT EXISTS idx_chat_error
    ON chat_messages (error) WHERE error IS NOT NULL;

-- Intent breakdown
CREATE INDEX IF NOT EXISTS idx_chat_intent
    ON chat_messages (intent) WHERE intent IS NOT NULL;