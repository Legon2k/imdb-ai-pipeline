package telemetry

import (
	"context"
	"strconv"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

// ExtractTraceContext extracts and injects traceparent from a W3C traceparent header into the context.
// This mirrors Python's TraceContextTextMapPropagator.extract() behavior.
func ExtractTraceContext(ctx context.Context, traceparent string) context.Context {
	if traceparent == "" {
		return ctx
	}

	// Split the traceparent string manually
	parts := strings.Split(traceparent, "-")
	if len(parts) < 4 {
		// Fallback to default propagator if format is incomplete
		textMapCarrier := propagation.MapCarrier{
			"traceparent": traceparent,
		}
		return otel.GetTextMapPropagator().Extract(ctx, textMapCarrier)
	}

	// Extract fields
	// version := parts[0] // currently unused
	traceIDStr := parts[1]
	spanIDStr := parts[2]
	traceFlagsStr := parts[3]

	if traceIDStr != "" && spanIDStr != "" {
		traceID, err := trace.TraceIDFromHex(traceIDStr)
		if err != nil {
			// Log error if needed, but continue without trace context
			return ctx
		}

		spanID, err := trace.SpanIDFromHex(spanIDStr)
		if err != nil {
			// Log error if needed, but continue without trace context
			return ctx
		}

		traceFlagsVal, err := strconv.ParseUint(traceFlagsStr, 16, 8)
		if err != nil {
			// Log error if needed, but continue without trace context
			return ctx
		}
		traceFlags := trace.TraceFlags(byte(traceFlagsVal))

		parentSpanContext := trace.NewSpanContext(trace.SpanContextConfig{
			TraceID:    traceID,
			SpanID:     spanID,
			TraceFlags: traceFlags,
			Remote:     true,
		})
		return trace.ContextWithRemoteSpanContext(ctx, parentSpanContext)
	}

	// Fallback to default propagator if manual parsing fails or is incomplete
	textMapCarrier := propagation.MapCarrier{
		"traceparent": traceparent,
	}
	return otel.GetTextMapPropagator().Extract(ctx, textMapCarrier)
}

// InjectTraceContext extracts the current span context and returns it as a traceparent header.
// This mirrors Python's get_traceparent() behavior.
func InjectTraceContext(ctx context.Context) string {
	carrier := propagation.MapCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)
	return carrier.Get("traceparent")
}

// GetCurrentSpanContext returns the span context from the current context
func GetCurrentSpanContext(ctx context.Context) trace.SpanContext {
	return trace.SpanContextFromContext(ctx)
}

