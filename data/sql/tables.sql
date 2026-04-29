-- Store a word
CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    word TEXT UNIQUE NOT NULL,
    senses TEXT NOT NULL,
    spelling TEXT NOT NULL,
    forms TEXT,
    occurrence INT, -- occurring frequency
    jlpt_level TEXT,
    audio_mapping TEXT[]
);


-- User (admin role) uploads a book
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
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
