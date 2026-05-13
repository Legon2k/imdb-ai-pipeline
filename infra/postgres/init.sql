-- infra/postgres/init.sql

CREATE TABLE IF NOT EXISTS movies (
    id SERIAL PRIMARY KEY,
    imdb_id VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    rating NUMERIC(3, 1),
    description TEXT,
    ai_summary TEXT, -- Сюда локальная LLM будет писать саммари
    status VARCHAR(50) DEFAULT 'pending', -- Статусы: pending, processing, completed, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрого поиска по imdb_id (полезно для базы скрапера)
CREATE INDEX idx_movies_imdb_id ON movies(imdb_id);
-- Индекс по статусу, чтобы .NET Worker быстро находил задачи
CREATE INDEX idx_movies_status ON movies(status);