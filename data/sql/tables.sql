-- Store a word
CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY NOT NULL,
    word TEXT UNIQUE NOT NULL,
    senses TEXT NOT NULL,
    spelling TEXT NOT NULL,
    forms TEXT,
    occurrence INT, -- occurring frequency
    jlpt_level TEXT,
    audio_mapping TEXT[],
    quized INT, -- quiz_ed times, +1 if correct, -1 if fail
    last_tested TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- the last time this word has been quiz_ed
    star BOOLEAN,
    priority NUMERIC    -- use occurrence and quized to calc
);

-- Store a book
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY NOT NULL,
    created TIMESTAMP NOT NULL DEFAULT now(),
    name TEXT UNIQUE NOT NULL,
    star BOOLEAN,
    content TEXT    -- the entire book content, the limit is 1GB which no books achieve
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
    occurrence INT,     -- count sentence occrences to decide if is popular or not (current auto alg)
    quized INT,
    star BOOLEAN DEFAULT FALSE    -- set if sentence is popular (manual set if want)
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


-- Store the audio, words can have multiple letters, but only composed of the ones in the alphabets
-- CREATE TABLE IF NOT EXISTS audio (
--     id SERIAL PRIMARY KEY,
--     romaji TEXT NOT NULL
--     sound BYTEA NOT NULL
-- );
