-- infra/postgres/init.sql

CREATE TABLE IF NOT EXISTS movies (
    id SERIAL PRIMARY KEY,
    imdb_id VARCHAR(50) UNIQUE NOT NULL,
    rank INTEGER,
    title VARCHAR(255) NOT NULL,
    rating NUMERIC(3, 1),
    votes VARCHAR(50),
    image_url TEXT,
    ai_summary TEXT, -- For future LLM integration
    status VARCHAR(50) DEFAULT 'pending', -- pending, processing, completed, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_movies_imdb_id ON movies(imdb_id);
CREATE INDEX IF NOT EXISTS idx_movies_status ON movies(status);