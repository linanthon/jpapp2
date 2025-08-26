DO
$$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_matviews
        WHERE matviewname = 'word_priority'
    ) THEN
        -- Create the view if it doesn't exist
        CREATE MATERIALIZED VIEW word_priority AS
        SELECT id, word, ({formula}) AS priority
        FROM {table};
    ELSE
        -- Refresh the existing view
        REFRESH MATERIALIZED VIEW word_priority;
    END IF;
END
$$;
COMMIT;