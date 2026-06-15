package telemetry

import (
	"log/slog"
	"os"
	"time"
)

// ConfigureLogger sets up the global slog JSON logger with a unified schema and metadata [3].
func ConfigureLogger(version string, level slog.Level) *slog.Logger {
	opts := &slog.HandlerOptions{
		Level: level,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Map slog internal keys to match Python API Gateway schema
			switch a.Key {
			case slog.TimeKey:
				// Format timestamp as UTC ISO 8601 with milliseconds [1]
				return slog.String("timestamp", a.Value.Time().UTC().Format(time.RFC3339Nano))
			case slog.LevelKey:
				return slog.String("level", a.Value.String())
			case slog.MessageKey:
				return slog.String("message", a.Value.String())
			}
			return a
		},
	}

	// Create JSON Handler writing directly to stdout [5]
	jsonHandler := slog.NewJSONHandler(os.Stdout, opts)

	// Inject global tracing and version metadata
	logger := slog.New(jsonHandler).With(
		slog.String("service_name", "worker-go"),
		slog.String("version", version),
	)

	// Set as global default logger for package-level slog calls [3]
	slog.SetDefault(logger)

	return logger
}
