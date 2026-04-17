-- migrations/002_add_intent_validation_to_chat_messages.sql
-- ────────────────────────────────────────────────────────
-- Adds intent and validation_errors columns to the existing
-- chat_messages table (if it was created by migration 001).
--
-- Safe to run multiple times (uses IF NOT EXISTS / column checks).
--
-- Run:
--   psql -d your_db -f migrations/002_add_intent_validation_to_chat_messages.sql

DO $$
BEGIN
    -- Add intent column if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_messages' AND column_name = 'intent'
    ) THEN
        ALTER TABLE chat_messages ADD COLUMN intent VARCHAR(50);
        CREATE INDEX IF NOT EXISTS idx_chat_intent
            ON chat_messages (intent) WHERE intent IS NOT NULL;
        RAISE NOTICE 'Added intent column';
    END IF;

    -- Add validation_errors column if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_messages' AND column_name = 'validation_errors'
    ) THEN
        ALTER TABLE chat_messages ADD COLUMN validation_errors JSONB;
        RAISE NOTICE 'Added validation_errors column';
    END IF;
END
$$;