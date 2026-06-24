// File: src/worker_go/internal/redis/consumer.go
package redis

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/db"
	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/model"
	"github.com/Legon2k/imdb-ai-pipeline/src/worker_go/internal/telemetry"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

const PayloadField = "payload"
const logBatchSize = 1000

// MoviesProcessedTotal tracks raw processed message counts
var MoviesProcessedTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "movies_processed_total",
		Help: "Total movies processed by the Go worker by outcome.",
	},
	[]string{"status"},
)

// MessageProcessingDuration tracks high-resolution latency percentiles
var MessageProcessingDuration = prometheus.NewHistogram(
	prometheus.HistogramOpts{
		Name:    "message_processing_duration_seconds",
		Help:    "Latency of a single message processing run (from read to ACK) in seconds.",
		Buckets: []float64{0.00002, 0.00005, 0.0001, 0.0002, 0.0004, 0.0008, 0.0015, 0.003, 0.006, 0.012, 0.025, 0.05, 0.1},
	},
)

type Worker struct {
	redisClient    *redis.Client
	repo           *db.Repository
	streamName     string
	consumerGroup  string
	consumerName   string
	logger         *slog.Logger
	tracer         trace.Tracer
	simulateDbSave bool
}

func NewWorker(rc *redis.Client, repo *db.Repository, stream, group, consumer string, logger *slog.Logger, tracer trace.Tracer, simulateDbSave bool) *Worker {
	return &Worker{
		redisClient:    rc,
		repo:           repo,
		streamName:     stream,
		consumerGroup:  group,
		consumerName:   consumer,
		logger:         logger,
		tracer:         tracer,
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
	// Start high-resolution latency timer
	start := time.Now()

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

	// --- OPENTELEMETRY CONTEXT PROPAGATION ---
	var traceparent string

	// Attempt 1: Extract from the JSON payload (populated by FastAPI /enrich)
	var rawMap map[string]interface{}
	if err := json.Unmarshal([]byte(payloadStr), &rawMap); err == nil {
		if tp, ok := rawMap["traceparent"].(string); ok {
			traceparent = tp
		}
	}

	// Attempt 2: Extract from Redis Stream entry metadata fields (populated by python_scraper)
	if traceparent == "" {
		if tpVal, exists := entry.Values["traceparent"]; exists {
			traceparent, _ = tpVal.(string)
		}
	}

	// Instantiate a task-scoped contextual logger to encapsulate trace metadata [3]
	taskLogger := w.logger
	if traceparent != "" {
		if traceID, spanID := parseTraceparent(traceparent); traceID != "" {
			taskLogger = w.logger.With(
				slog.String("traceID", traceID),
				slog.String("spanID", spanID),
			)
		}
	}	

	// Extract OTel trace context from traceparent header and inject into context
	ctx = telemetry.ExtractTraceContext(ctx, traceparent)

	// Capture the extracted span context to use as a Link
	parentSpanContext := trace.SpanContextFromContext(ctx)
	
	// Log trace context extraction result at INFO level for visibility
	w.logger.Info("trace context extraction result",
		slog.String("traceparent_input", traceparent),
		slog.String("extracted_traceID", parentSpanContext.TraceID().String()),
		slog.String("extracted_spanID", parentSpanContext.SpanID().String()),
		slog.Bool("is_valid", parentSpanContext.IsValid()),
		slog.Bool("is_remote", parentSpanContext.IsRemote()),
	)
	
	// Create main processing span for this message as a new root span, linking to the incoming trace
	var msgCtx context.Context
	var msgSpan trace.Span
	if parentSpanContext.IsValid() {
		msgCtx, msgSpan = w.tracer.Start(context.Background(), "process_movie_message", trace.WithLinks(trace.Link{SpanContext: parentSpanContext}))
		w.logger.Info("created root span with link to upstream trace",
			slog.String("root_span_traceID", trace.SpanContextFromContext(msgCtx).TraceID().String()),
			slog.String("linked_traceID", parentSpanContext.TraceID().String()),
		)
	} else {
		msgCtx, msgSpan = w.tracer.Start(context.Background(), "process_movie_message")
		w.logger.Info("created root span without link (no valid traceparent)")
	}
	defer msgSpan.End()

	// Set message processing span attributes
	msgSpan.SetAttributes(
		attribute.String("messaging.system", "redis"),
		attribute.String("messaging.destination", w.streamName),
		attribute.String("messaging.message_id", entry.ID),
	)


	// ------------------------------------------------

	var movie model.MoviePayload
	if err := json.Unmarshal([]byte(payloadStr), &movie); err != nil {
		MoviesProcessedTotal.WithLabelValues("validation_error").Inc()
		if taskLogger.Enabled(msgCtx, slog.LevelDebug) {
			taskLogger.Debug("skipping stream entry: invalid movie payload", slog.String("message_id", entry.ID), slog.String("error", err.Error()))
		}
		return w.acknowledge(ctx, entry.ID)
	}

	// Validate against contract rules
	if err := movie.Validate(); err != nil {
		MoviesProcessedTotal.WithLabelValues("validation_error").Inc()
		if taskLogger.Enabled(msgCtx, slog.LevelDebug) {
			taskLogger.Debug("skipping stream entry: contract validation failed", slog.String("message_id", entry.ID), slog.String("error", err.Error()))
		}
		return w.acknowledge(ctx, entry.ID)
	}

	// Create a child span for database operation using OpenTelemetry
	dbCtx, span := w.tracer.Start(msgCtx, "save_movie_to_database")
	defer span.End()

	// Set span attributes for observability
	span.SetAttributes(
		attribute.String("db.system", "postgresql"),
		attribute.String("db.operation", "upsert"),
		attribute.String("movie.imdb_id", movie.ImdbId),
		attribute.String("movie.title", movie.Title),
	)

	// Inject the child span's traceparent for database persistence
	movie.TraceParent = telemetry.InjectTraceContext(dbCtx)

	// SQL Write (or simulated bypass) using the child span context
	if !w.simulateDbSave {
		if err := w.repo.SaveMovieToDatabase(dbCtx, &movie); err != nil {
			MoviesProcessedTotal.WithLabelValues("db_error").Inc()
			return fmt.Errorf("failed to save movie to database: %w", err)
		}
	}

	// Acknowledge stream entry
	if err := w.acknowledge(ctx, entry.ID); err != nil {
		return err
	}

	// Record success metric and measure processing latency
	MoviesProcessedTotal.WithLabelValues("success").Inc()
	MessageProcessingDuration.Observe(time.Since(start).Seconds())

	if taskLogger.Enabled(ctx, slog.LevelDebug) {
		taskLogger.Debug("saved to DB and acknowledged stream entry", slog.String("title", movie.Title), slog.String("message_id", entry.ID))
	}
	// Increment message counter
	*msgCounter++

	// Check if batch limit reached
	if *msgCounter%int64(logBatchSize) == 0 {
		elapsed := time.Since(*batchStart)
		rps := float64(logBatchSize) / elapsed.Seconds()
		taskLogger.Info("[BATCH] Processed: " + fmt.Sprint(*msgCounter) + " | Batch Time: " + fmt.Sprintf("%.2f", elapsed.Seconds()) + "s | Batch RPS: " + fmt.Sprintf("%.2f", rps))
		*batchStart = time.Now()
	}

	return nil
}

func (w *Worker) acknowledge(ctx context.Context, messageID string) error {
	return w.redisClient.XAck(ctx, w.streamName, w.consumerGroup, messageID).Err()
}

// parseTraceparent extracts traceID and spanID from a W3C traceparent header [1].
// Format: version-trace_id-parent_id-trace_flags (e.g. 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01)
func parseTraceparent(traceparent string) (string, string) {
	parts := strings.Split(traceparent, "-")
	if len(parts) >= 3 && len(parts[1]) == 32 && len(parts[2]) == 16 {
		return parts[1], parts[2]
	}
	return "", ""
}

// parseTraceparentFields extracts all fields from a W3C traceparent header.
// Format: version-trace_id-parent_id-trace_flags
func parseTraceparentFields(traceparent string) (version, traceID, spanID, traceFlags string) {
	parts := strings.Split(traceparent, "-")
	if len(parts) >= 4 {
		return parts[0], parts[1], parts[2], parts[3]
	}
	return "", "", "", ""
}
