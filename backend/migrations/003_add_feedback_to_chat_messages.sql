-- migrations/003_add_feedback_to_chat_messages.sql
-- ───────────────────────────────────────────────
-- Adds per-message user feedback columns to chat_messages.
--
-- Run:
--   psql -d your_db -f migrations/003_add_feedback_to_chat_messages.sql

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_messages' AND column_name = 'feedback_score'
    ) THEN
        ALTER TABLE chat_messages ADD COLUMN feedback_score SMALLINT;
        RAISE NOTICE 'Added feedback_score column';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_messages' AND column_name = 'feedback_at'
    ) THEN
        ALTER TABLE chat_messages ADD COLUMN feedback_at TIMESTAMPTZ;
        RAISE NOTICE 'Added feedback_at column';
    END IF;
END
$$;