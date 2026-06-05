package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/config"
	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/db"
	rWorker "github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/redis"
	"github.com/redis/go-redis/v9"
)

// Global variable populated at compile time via -ldflags
var Version = "0.0.0-dev"

func main() {
	// Logger initialization (JSON matches modern observability stacks)
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	// Load settings
	cfg, err := config.Load()
	if err != nil {
		logger.Error("failed to load configuration", slog.String("error", err.Error()))
		os.Exit(1)
	}

	// Graceful setup
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger.Info("IMDB Worker started",
		slog.String("version", Version),
		slog.String("stream", cfg.StreamName),
		slog.String("group", cfg.ConsumerGroup),
		slog.String("consumer", cfg.ConsumerName),
	)

	// DB Setup
	repo, err := db.NewRepository(ctx, cfg.GetPgConnectionString())
	if err != nil {
		logger.Error("database setup failed", slog.String("error", err.Error()))
		os.Exit(1)
	}
	defer repo.Close()

	// Redis Setup
	rClient := redis.NewClient(&redis.Options{
		Addr: cfg.GetRedisAddr(),
	})
	if err := rClient.Ping(ctx).Err(); err != nil {
		logger.Error("redis connection failed", slog.String("error", err.Error()))
		os.Exit(1)
	}
	defer rClient.Close()

	// Initialize Worker
	worker := rWorker.NewWorker(rClient, repo, cfg.StreamName, cfg.ConsumerGroup, cfg.ConsumerName, logger)
	if err := worker.EnsureConsumerGroup(ctx); err != nil {
		logger.Error("failed to verify consumer group", slog.String("error", err.Error()))
		os.Exit(1)
	}

	// Execution Loop
	go worker.Start(ctx)

	// Block until signal is captured
	<-ctx.Done()
	logger.Info("shutdown request received, cleaning up resources...")

	// Force exit timeout limit
	_, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	logger.Info("worker service has stopped cleanly")
}
