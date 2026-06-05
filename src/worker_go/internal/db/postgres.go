package db

import (
	"context"
	"fmt"

	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/model"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(ctx context.Context, connString string) (*Repository, error) {
	pool, err := pgxpool.New(ctx, connString)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		return nil, fmt.Errorf("database ping failed: %w", err)
	}

	return &Repository{pool: pool}, nil
}

func (r *Repository) Close() {
	r.pool.Close()
}

// SaveMovieToDatabase matches .NET SaveMovieToDatabaseAsync behavior exactly
func (r *Repository) SaveMovieToDatabase(ctx context.Context, movie *model.MoviePayload) error {
	const sql = `
		INSERT INTO movies (imdb_id, rank, title, rating, votes, image_url, status)
		VALUES ($1, $2, $3, $4, $5, $6, 'pending')
		ON CONFLICT (imdb_id) DO UPDATE 
		SET rank = EXCLUDED.rank,
			rating = EXCLUDED.rating,
			votes = EXCLUDED.votes,
			updated_at = CURRENT_TIMESTAMP;`

	_, err := r.pool.Exec(ctx, sql,
		movie.ImdbId,
		movie.Rank,
		movie.Title,
		movie.Rating,
		movie.Votes,
		movie.ImageUrl,
	)
	if err != nil {
		return fmt.Errorf("db upsert error: %w", err)
	}

	return nil
}
