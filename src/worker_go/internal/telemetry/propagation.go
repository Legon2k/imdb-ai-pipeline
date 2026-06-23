package telemetry

import (
	"context"

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

	// Create carrier with traceparent header
	textMapCarrier := propagation.MapCarrier{
		"traceparent": traceparent,
	}

	// Use the W3C Trace Context propagator to extract context
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
