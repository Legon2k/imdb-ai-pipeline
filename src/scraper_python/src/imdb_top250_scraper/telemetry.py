"""
OpenTelemetry tracing initialization and context management for the IMDb scraper.
Handles trace context propagation from environment (SCRAPER_TRACEPARENT) and
provides utilities for trace context injection into logs.
"""

import logging
import os

from opentelemetry import context, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)


def setup_otel_scraper(service_name: str = "imdb-scraper") -> trace.Tracer:
    """
    Initializes OpenTelemetry TracerProvider and OTLP Exporter pointing to Alloy.
    Sets up the global trace context that can be populated from environment.
    """
    try:
        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)

        # Point to Alloy gRPC receiver inside Docker network
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        logger.info(f"OpenTelemetry successfully initialized. Exporting to {otlp_endpoint}")
        return trace.get_tracer(service_name)
    except Exception as exc:
        logger.warning(f"Failed to initialize OpenTelemetry. Falling back to No-Op: {exc}")
        # Standard OTel fallback: get_tracer behaves as No-Op if provider was not registered
        return trace.get_tracer(service_name)


def initialize_trace_from_env() -> str | None:
    """
    Initializes trace context from SCRAPER_TRACEPARENT environment variable.
    If provided and valid, injects it into the current context.
    Returns the traceparent string if successfully initialized.
    """
    traceparent = os.getenv("SCRAPER_TRACEPARENT", "").strip()

    if not traceparent:
        logger.debug("SCRAPER_TRACEPARENT not set. Starting with new trace.")
        return None

    try:
        # Extract traceparent from environment
        # Format: traceparent header (00-traceID-spanID-traceflags)
        propagator = TraceContextTextMapPropagator()
        carrier = {"traceparent": traceparent}

        # Extract the trace context from the carrier
        ctx = propagator.extract(carrier)

        # Attach the extracted context to the current context
        context.attach(ctx)

        logger.debug(f"Initialized trace context from SCRAPER_TRACEPARENT: {traceparent}")
        return traceparent
    except Exception as exc:
        logger.warning(f"Failed to parse SCRAPER_TRACEPARENT: {exc}. Starting fresh trace.")
        return None


def get_traceparent() -> str:
    """
    Extracts the active OpenTelemetry traceparent from current span context.
    Returns the traceparent header string or empty string if no active trace.
    """
    carrier = {}
    TraceContextTextMapPropagator().inject(carrier)
    return carrier.get("traceparent", "")


def get_trace_ids() -> dict[str, str]:
    """
    Gets current trace ID and span ID from the active span context.
    Returns a dict with traceID and spanID keys for structured logging.
    """
    current_span = trace.get_current_span()
    span_context = current_span.get_span_context() if current_span else None

    if span_context and span_context.is_valid:
        return {
            "traceID": trace.format_trace_id(span_context.trace_id),
            "spanID": trace.format_span_id(span_context.span_id),
        }

    return {}
