-- Find popular sentence
SELECT word_id, sentence, COUNT(*) as count
FROM word_sentences
GROUP BY word_id, sentence
HAVING count > threshold;

-- Lookup all sentences contain this word ID
SELECT s.*
FROM sentences AS s
JOIN sentence_words AS sw ON s.id = sw.sentence_id
WHERE sw.word_id = 123;

-- Lookup all words of this sentence ID
SELECT w.*
FROM words AS w
JOIN sentence_words AS sw ON w.id = sw.word_id
WHERE sw.sentence_id = 456;


-- Start WSL postgres server
-- sudo service postgresql start