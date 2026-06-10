package redis

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/db"
	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/model"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/v9"
)

const PayloadField = "payload"
const logBatchSize = 1000

var MoviesProcessedTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "movies_processed_total",
		Help: "Total movies processed by the Go worker by outcome.",
	},
	[]string{"status"},
)

type Worker struct {
	redisClient    *redis.Client
	repo           *db.Repository
	streamName     string
	consumerGroup  string
	consumerName   string
	logger         *slog.Logger
	simulateDbSave bool
}

func NewWorker(rc *redis.Client, repo *db.Repository, stream, group, consumer string, logger *slog.Logger, simulateDbSave bool) *Worker {
	return &Worker{
		redisClient:    rc,
		repo:           repo,
		streamName:     stream,
		consumerGroup:  group,
		consumerName:   consumer,
		logger:         logger,
		simulateDbSave: simulateDbSave,
	}
}

func (w *Worker) EnsureConsumerGroup(ctx context.Context) error {
	err := w.redisClient.XGroupCreateMkStream(ctx, w.streamName, w.consumerGroup, "0-0").Err()
	if err != nil && err.Error() != "BUSYGROUP Consumer Group name already exists" {
		return fmt.Errorf("failed to create redis consumer group: %w", err)
	}
	return nil
}

func (w *Worker) Start(ctx context.Context) {
	var msgCounter int64 = 0
	batchStart := time.Now()

	for {
		select {
		case <-ctx.Done():
			w.logger.Info("stopping consumer loop due to cancellation request")
			return
		default:
			err := w.pollAndProcess(ctx, &msgCounter, &batchStart)
			if err != nil {
				w.logger.Error("error processing message. Retrying...", slog.String("error", err.Error()))

				select {
				case <-ctx.Done():
					return
				case <-time.After(5 * time.Second):
				}
			}
		}
	}
}

func (w *Worker) pollAndProcess(ctx context.Context, msgCounter *int64, batchStart *time.Time) error {
	// 1. Try reading new messages (">")
	entries, err := w.readFromStream(ctx, ">")
	if err != nil {
		return err
	}

	// 2. If no new messages, read pending messages specific to this consumer ("0")
	if len(entries) == 0 {
		entries, err = w.readFromStream(ctx, "0")
		if err != nil {
			return err
		}
	}

	// 3. Process the read entry if exists
	if len(entries) > 0 {
		return w.processEntry(ctx, entries[0], msgCounter, batchStart)
	}

	// 4. If no entries found, wait 1 second
	select {
	case <-ctx.Done():
	case <-time.After(1 * time.Second):
	}
	return nil
}

func (w *Worker) readFromStream(ctx context.Context, id string) ([]redis.XMessage, error) {
	streams, err := w.redisClient.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    w.consumerGroup,
		Consumer: w.consumerName,
		Streams:  []string{w.streamName, id},
		Count:    1,
		Block:    -1, // Non-blocking read to mirror StackExchange.Redis
	}).Result()

	if err != nil {
		if errors.Is(err, redis.Nil) {
			return nil, nil
		}
		return nil, err
	}

	if len(streams) > 0 && len(streams[0].Messages) > 0 {
		return streams[0].Messages, nil
	}

	return nil, nil
}

func (w *Worker) processEntry(ctx context.Context, entry redis.XMessage, msgCounter *int64, batchStart *time.Time) error {
	rawPayload, exists := entry.Values[PayloadField]
	if !exists {
		MoviesProcessedTotal.WithLabelValues("validation_error").Inc()
		if w.logger.Enabled(ctx, slog.LevelDebug) {
			w.logger.Debug("skipping stream entry: missing payload field", slog.String("message_id", entry.ID))
		}
		return w.acknowledge(ctx, entry.ID)
	}

	payloadStr, ok := rawPayload.(string)
	if !ok {
		MoviesProcessedTotal.WithLabelValues("validation_error").Inc()
		if w.logger.Enabled(ctx, slog.LevelDebug) {
			w.logger.Debug("skipping stream entry: invalid payload type", slog.String("message_id", entry.ID))
		}
		return w.acknowledge(ctx, entry.ID)
	}

	var movie model.MoviePayload
	if err := json.Unmarshal([]byte(payloadStr), &movie); err != nil {
		MoviesProcessedTotal.WithLabelValues("validation_error").Inc()
		if w.logger.Enabled(ctx, slog.LevelDebug) {
			w.logger.Debug("skipping stream entry: invalid movie payload", slog.String("message_id", entry.ID), slog.String("error", err.Error()))
		}
		return w.acknowledge(ctx, entry.ID)
	}

	// Validate against contract rules
	if err := movie.Validate(); err != nil {
		MoviesProcessedTotal.WithLabelValues("validation_error").Inc()
		if w.logger.Enabled(ctx, slog.LevelDebug) {
			w.logger.Debug("skipping stream entry: contract validation failed", slog.String("message_id", entry.ID), slog.String("error", err.Error()))
		}
		return w.acknowledge(ctx, entry.ID)
	}

	// SQL Write
	if !w.simulateDbSave {
		if err := w.repo.SaveMovieToDatabase(ctx, &movie); err != nil {
			MoviesProcessedTotal.WithLabelValues("db_error").Inc()
			return fmt.Errorf("failed to save movie to database: %w", err)
		}
	}

	// Acknowledge stream entry
	if err := w.acknowledge(ctx, entry.ID); err != nil {
		return err
	}

	MoviesProcessedTotal.WithLabelValues("success").Inc()
	if w.logger.Enabled(ctx, slog.LevelDebug) {
		w.logger.Debug("saved to DB and acknowledged stream entry", slog.String("title", movie.Title), slog.String("message_id", entry.ID))
	}
	// Increment message counter
	*msgCounter++

	// Check if batch limit reached
	if *msgCounter%int64(logBatchSize) == 0 {
		elapsed := time.Since(*batchStart)
		rps := float64(logBatchSize) / elapsed.Seconds()
		w.logger.Info("[BATCH] Processed: " + fmt.Sprint(*msgCounter) + " | Batch Time: " + fmt.Sprintf("%.2f", elapsed.Seconds()) + "s | Batch RPS: " + fmt.Sprintf("%.2f", rps))
		*batchStart = time.Now()
	}

	return nil
}

func (w *Worker) acknowledge(ctx context.Context, messageID string) error {
	return w.redisClient.XAck(ctx, w.streamName, w.consumerGroup, messageID).Err()
}
