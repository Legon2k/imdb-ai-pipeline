# OpenTelemetry Integration for IMDb Scraper

## Overview

The IMDb scraper now includes comprehensive OpenTelemetry (OTel) tracing support, enabling distributed tracing across the microservices pipeline. The tracer automatically captures and correlates logs with trace IDs and span IDs.

## Features

- **Automatic trace context initialization** from `SCRAPER_TRACEPARENT` environment variable
- **Structured JSON logging** with injected trace IDs and span IDs
- **OTLP export** to Alloy (OpenTelemetry Collector)
- **Span instrumentation** for key operations:
  - `scrape_imdb_top_250` - main scraping operation
  - `scrape_once` - individual scraping attempt
  - `extract_movies` - DOM extraction
  - `publish_to_redis` - Redis publishing

## Environment Variables

### Required (Optional with defaults)
- `OTEL_EXPORTER_OTLP_ENDPOINT` - Alloy gRPC endpoint (default: `http://alloy:4317`)
- `SCRAPER_TRACEPARENT` - W3C Trace Context header to propagate trace from parent service (format: `00-<traceID>-<spanID>-01`)

## Usage Examples

### Manual trace initialization

```python
from imdb_top250_scraper.telemetry import setup_otel_scraper, initialize_trace_from_env, get_traceparent

# Initialize OpenTelemetry
tracer = setup_otel_scraper(service_name="imdb-scraper")

# Initialize trace context from environment
traceparent = initialize_trace_from_env()

# Get current traceparent
current_traceparent = get_traceparent()
```

### Docker usage with trace propagation

```bash
# Run scraper with trace context from parent service
docker run \
  -e SCRAPER_TRACEPARENT="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -e OTEL_EXPORTER_OTLP_ENDPOINT="http://alloy:4317" \
  imdb-scraper:latest --chart=top
```

### FastAPI integration example

The FastAPI API (`api_fastapi`) already injects trace context when triggering scraper:

```python
from imdb_top250_scraper.telemetry import get_traceparent

# Extract current traceparent
traceparent = get_traceparent()

# Pass to scraper via environment
client.containers.run(
    image="imdb-scraper:latest",
    environment={
        "SCRAPER_TRACEPARENT": traceparent,
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://alloy:4317",
    }
)
```

## Log Output Format

All logs are output in structured JSON format with trace correlation:

```json
{
  "timestamp": "2026-06-21T10:30:45.123Z",
  "level": "INFO",
  "logger": "imdb_top250_scraper.scraper",
  "message": "Successfully published 250 movies to Redis.",
  "service_name": "imdb-scraper",
  "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanID": "00f067aa0ba902b7"
}
```

When no trace context is provided, logs will not include `traceID` and `spanID` fields.

## Span Attributes

### scrape_imdb_top_250
- `chart` - Chart name (top, moviemeter, toptv, tvmeter)
- `include_images` - Whether images are included
- `limit` - Movie limit
- `retries` - Number of retry attempts
- `timeout_seconds` - Page operation timeout

### scrape_once
- `chart.url` - IMDb URL
- `chart.description` - Chart description
- `chart.limit` - Expected movie count
- `result_count` - Actual extracted movie count

### extract_movies
- `include_images` - Whether images are included
- `limit` - Movie limit
- `extracted_count` - Number of extracted movies

### publish_to_redis
- `movie_count` - Total movies to publish
- `published_count` - Successfully published count

## Integration with Alloy/Prometheus/Grafana

Traces are automatically exported to Alloy via gRPC. The Alloy instance then routes traces to your observability backend (Tempo, Jaeger, etc.).

### Configuration in docker-compose.yml

```yaml
services:
  scraper:
    image: imdb-scraper:latest
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: http://alloy:4317
      SCRAPER_TRACEPARENT: ${TRACE_PARENT:-}
```

## Development

### Testing trace context extraction

```python
import os
from imdb_top250_scraper.telemetry import initialize_trace_from_env, get_traceparent

# Set a valid W3C traceparent
os.environ["SCRAPER_TRACEPARENT"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

# Initialize
traceparent = initialize_trace_from_env()
print(f"Initialized: {traceparent}")

# Get current traceparent
current = get_traceparent()
print(f"Current: {current}")
```

## Troubleshooting

### Traces not appearing in backend
1. Verify `OTEL_EXPORTER_OTLP_ENDPOINT` is correct and Alloy is reachable
2. Check logs for "Failed to initialize OpenTelemetry" messages
3. Ensure OpenTelemetry SDK is installed: `pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp`

### SCRAPER_TRACEPARENT not being used
1. Verify the environment variable format is valid W3C Trace Context
2. Check logs for "Failed to parse SCRAPER_TRACEPARENT" warning
3. New trace will be started if parsing fails
