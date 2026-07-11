-- migrations/004_create_sql_corrections_table.sql
-- ------------------------------------------------
-- Records every case where an automatic schema-drift correction or
-- department-scope injection actually changed the LLM's generated SQL.
-- Feeds the planned sqlcoder/llama3.2 fine-tuning dataset (question ->
-- corrected SQL pairs) — see core/sql_corrections.py and
-- core/sql_correction_log.py.
--
-- Run:
--   psql -d your_db -f migrations/004_create_sql_corrections_table.sql

CREATE TABLE IF NOT EXISTS sql_corrections (
    id               SERIAL PRIMARY KEY,
    user_id          TEXT,
    session_id       TEXT,
    question         TEXT NOT NULL,
    original_sql     TEXT NOT NULL,
    corrected_sql    TEXT NOT NULL,
    rule_names       JSONB,
    department_code  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'sql_corrections' AND indexname = 'idx_sql_corrections_created_at'
    ) THEN
        CREATE INDEX idx_sql_corrections_created_at ON sql_corrections (created_at);
        RAISE NOTICE 'Added idx_sql_corrections_created_at index';
    END IF;
END
$$;
