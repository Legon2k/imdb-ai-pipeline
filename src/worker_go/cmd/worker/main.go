package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/config"
	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/db"
	rWorker "github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/redis"
	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/telemetry" // <--- Импорт пакета телеметрии
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
)

func main() {
	// Capture cold start time
	startTime := time.Now()

	// Read version from environment variable with fallback (moved up to inject into logger)
	version := os.Getenv("APP_VERSION")
	if version == "" {
		version = "0.0.0-dev"
	}

	// Load settings first to get log level
	cfg, err := config.Load()
	if err != nil {
		// Fallback logger for initialization errors (unformatted plain JSON)
		fallbackLogger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
		fallbackLogger.Error("failed to load configuration", slog.String("error", err.Error()))
		os.Exit(1)
	}

	// Standardize structured JSON logger with dynamic level and global metadata
	logger := telemetry.ConfigureLogger(version, cfg.GetLogLevel())

	// Register Prometheus metrics
	prometheus.MustRegister(rWorker.MoviesProcessedTotal)
	prometheus.MustRegister(rWorker.MessageProcessingDuration)

	http.Handle("/metrics", promhttp.Handler())
	go func() {
		logger.Info("metrics server started", slog.String("address", ":2112"), slog.String("path", "/metrics"))
		if err := http.ListenAndServe(":2112", nil); err != nil {
			logger.Error("metrics server stopped unexpectedly", slog.String("error", err.Error()))
		}
	}()

	// Graceful setup
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger.Info("IMDB Worker started",
		slog.String("logLevel", cfg.LogLevel),
		slog.Bool("simulateDbSave", cfg.IsSimulateDbSave()),
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

	// Log cold start metric
	timeToReady := time.Since(startTime)
	logger.Info("cold start complete", slog.Int64("time_ms", timeToReady.Milliseconds()))

	defer rClient.Close()

	// Initialize Worker
	worker := rWorker.NewWorker(rClient, repo, cfg.StreamName, cfg.ConsumerGroup, cfg.ConsumerName, logger, cfg.IsSimulateDbSave())
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
