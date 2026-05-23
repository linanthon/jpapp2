CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION immutable_array_to_string(arr text[], sep text) 
RETURNS text AS $$
    SELECT array_to_string(arr, sep);
$$ LANGUAGE sql IMMUTABLE;

-- Store JLPT level
CREATE TABLE IF NOT EXISTS jlpt_levels (
    id SERIAL PRIMARY KEY,
    word TEXT UNIQUE NOT NULL,
    jlpt_level TEXT NOT NULL
);

-- Store a word
CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    word TEXT UNIQUE NOT NULL,
    senses TEXT NOT NULL,
    spelling TEXT NOT NULL,
    forms TEXT,
    occurrence INT, -- occurring frequency
    jlpt_level TEXT,
    audio_mapping TEXT[],
    romanji TEXT GENERATED ALWAYS AS (immutable_array_to_string(audio_mapping, '')) STORED
);

CREATE INDEX IF NOT EXISTS idx_words_word_trgm ON words USING gin (word gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_words_senses_trgm ON words USING gin (senses gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_words_spelling_trgm ON words USING gin (spelling gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_words_romanji_trgm ON words USING gin (romanji gin_trgm_ops);


-- User (admin role) uploads a book
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    idempotency_key UUID UNIQUE,
    object_name TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    modified_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Store the reference of a word and the books contain it
-- DEBATE: do we really need this???
CREATE TABLE IF NOT EXISTS word_book (
    word_id INT REFERENCES words(id) ON DELETE CASCADE,
    book_id INT REFERENCES books(id) ON DELETE CASCADE,
    PRIMARY KEY (word_id, book_id)  -- preventing duplicate pairs of (word-books)
);

-- Store the reference of a word and the sentences contain it
CREATE TABLE IF NOT EXISTS sentences (
    id SERIAL PRIMARY KEY,
    sentence TEXT NOT NULL,
    occurrence INT     -- count sentence occrences to decide if is popular or not (current auto alg)
);

-- Store the reference of a word and the sentence contains it
CREATE TABLE IF NOT EXISTS word_sentence (
    sentence_id INT REFERENCES sentences(id) ON DELETE CASCADE,
    word_id INT REFERENCES words(id) ON DELETE CASCADE,
    PRIMARY KEY (word_id, sentence_id)
);

-- Store the reference of a sentence and the book contains it
CREATE TABLE IF NOT EXISTS sentence_book (
    sentence_id INT REFERENCES sentences(id) ON DELETE CASCADE,
    book_id INT REFERENCES books(id) ON DELETE CASCADE,
    PRIMARY KEY (sentence_id, book_id)
);

-- Store user info
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    is_admin BOOLEAN DEFAULT FALSE,
    username TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_at TIMESTAMP,
    modified_at TIMESTAMP
);

-- Store users progress of word quiz
CREATE TABLE IF NOT EXISTS user_word_progress (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    word_id INT REFERENCES words(id) ON DELETE CASCADE,
    quized INT,     -- quiz_ed times, +1 if correct, -1 if fail
    last_tested TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- the last time this word has been quiz_ed
    star BOOLEAN,
    priority NUMERIC,    -- use occurrence and quized to calc
    PRIMARY KEY(user_id, word_id)
);

-- Store users progress of sentence quiz
CREATE TABLE IF NOT EXISTS user_sentence_progress (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    sentence_id INT REFERENCES sentences(id) ON DELETE CASCADE,
    quized INT,     -- quiz_ed times, +1 if correct, -1 if fail
    last_tested TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- the last time this word has been quiz_ed
    star BOOLEAN,
    priority NUMERIC,    -- use occurrence and quized to calc
    PRIMARY KEY(user_id, sentence_id)
);

-- Store users favorite books
CREATE TABLE IF NOT EXISTS user_book_star (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    book_id INT REFERENCES sentences(id) ON DELETE CASCADE,
    star BOOLEAN,
    PRIMARY KEY(user_id, book_id)
);

-- Parent request row for multi-file upload fan-out (idempotent per user + request key)
CREATE TABLE IF NOT EXISTS job_book_batches (
    id UUID PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,   -- QUEUED / RUNNING / FINISHED / FAILED
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, idempotency_key)
);

-- Child rows for each uploaded file in one batch request
CREATE TABLE IF NOT EXISTS job_book_batch_items (
    id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES job_book_batches(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    book_id INT REFERENCES books(id) ON DELETE SET NULL,
    process_job_id UUID,
    file_name TEXT NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    spool_path TEXT,
    object_name TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,   -- UPLOADING / QUEUED_PROCESS / PROCESSING / FINISHED / FAILED_UPLOAD / FAILED_PROCESS
    error TEXT,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_book_batch_items_batch_id ON job_book_batch_items(batch_id);

-- Job info for scraping JLPT level data
CREATE TABLE IF NOT EXISTS job_scrape (
    id UUID PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    idempotency_key TEXT NOT NULL,
    trigger_type TEXT,  -- MANUAL, SCHEDULED, STARTUP
    source TEXT,    -- wikipedia, jlpt_sensei, ...
    status TEXT,    -- QUEUED / SCRAPING / UPDATING_WORDS / FINISHED / FAILED
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, idempotency_key)
);

-- Job info for async TTS generation
CREATE TABLE IF NOT EXISTS job_tts (
    id UUID PRIMARY KEY,
    text TEXT NOT NULL,
    lang TEXT NOT NULL,
    voice_options JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,    -- QUEUED / PROCESSING / FINISHED / FAILED
    error TEXT,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_tts_created_at ON job_tts(created_at DESC);
