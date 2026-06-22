# Integration Guide: Trace Context Propagation from API to Scraper

## Quick Start

This guide shows how to propagate trace context from the FastAPI API to the IMDb scraper, enabling distributed tracing.

## How It Works

```
1. FastAPI (API Gateway)
   ↓ (extracts current traceparent)
   ↓
2. Spawns Docker Container (Scraper)
   ↓ (passes SCRAPER_TRACEPARENT env var)
   ↓
3. IMDb Scraper
   ↓ (initializes trace context from env)
   ↓ (all logs include traceID and spanID)
   ↓
4. Alloy (OpenTelemetry Collector)
   ↓ (receives traces via gRPC)
   ↓
5. Observability Backend (Tempo/Jaeger/etc)
   ↓ (visualizes distributed trace)
```

## Code Changes Already Made

✅ **api_fastapi/src/main.py** - Already has `get_traceparent()` and trace injection:
```python
traceparent = get_traceparent()  # Extract from current span
client.containers.run(
    image="imdb-ai-pipeline-scraper:latest",
    environment={
        "SCRAPER_TRACEPARENT": traceparent,  # Pass to scraper
    }
)
```

✅ **scraper_python/src/imdb_top250_scraper/cli.py** - Now initializes trace:
```python
tracer = setup_otel_scraper(service_name="imdb-scraper")
traceparent = initialize_trace_from_env()  # Gets from env var
```

✅ **scraper_python/src/imdb_top250_scraper/logger.py** - Now logs trace context:
```json
{
  "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanID": "00f067aa0ba902b7",
  ...
}
```

## Docker Compose Example

```yaml
services:
  scraper:
    image: imdb-ai-pipeline-scraper:latest
    environment:
      # Alloy endpoint for trace export
      OTEL_EXPORTER_OTLP_ENDPOINT: http://alloy:4317
      # Trace context from parent (API) service (set by docker.py client)
      SCRAPER_TRACEPARENT: ${TRACE_PARENT:-}
    networks:
      - imdb-network
```

## Testing the Integration

### 1. Local Testing (without Docker)

```bash
cd src/scraper_python

# Set a valid W3C traceparent
export SCRAPER_TRACEPARENT="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# Run scraper - it will use the provided traceparent
uv run imdb-top250-scraper --chart=top --limit=5
```

### 2. Docker Testing

```bash
# Build scraper image
docker build -t imdb-scraper:test -f Dockerfile .

# Run with trace context
docker run \
  -e OTEL_EXPORTER_OTLP_ENDPOINT="http://alloy:4317" \
  -e SCRAPER_TRACEPARENT="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  --network imdb-ai-pipeline_internal_network \
  imdb-scraper:test --chart=top --limit=5
```

### 3. Via FastAPI API

```bash
# Start API
cd src/api_fastapi
uv run uvicorn main:app --reload

# Trigger scraping - the API will automatically propagate trace context
curl -X POST http://localhost:8000/movies/scrape?chart=top
```

## Observability Output

### Logs with Trace Context (via ELK/Loki)

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

### Trace Visualization (via Grafana/Tempo)

Distributed trace showing:
```
GET /movies/scrape [API Gateway]
├─ enqueue_movie_task (span)
│  ├─ [traceparent]
│  └─ publish_to_redis (container)
└─ scrape_imdb_top_250 (Scraper)
   ├─ scrape_once
   │  ├─ extract_movies
   │  │  ├─ [DOM extraction]
   │  │  └─ [validation]
   │  └─ publish_to_redis
   │     ├─ [Redis XADD]
   │     └─ [batch commit]
   └─ [Result: 250 movies]
```

## Environment Variables Reference

| Variable | Source | Used By | Format |
|----------|--------|---------|--------|
| `SCRAPER_TRACEPARENT` | API (set during docker.run) | Scraper CLI | W3C Trace Context header |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | docker-compose.yml | Scraper/API | `http://alloy:4317` |

## Troubleshooting

### Traces not correlated across services

1. **Verify traceparent format**: Must be `00-<32-char-hex>-<16-char-hex>-01`
2. **Check OTEL_EXPORTER_OTLP_ENDPOINT**: Is Alloy reachable from container?
3. **Verify logs**: Check scraper logs for "Initialized trace context" message

### Logs missing traceID/spanID

- Trace context initialization failed (check "Failed to parse SCRAPER_TRACEPARENT" warning)
- OpenTelemetry SDK not properly initialized (check setup_otel_scraper logs)
- Using old API version that doesn't pass traceparent

### Docker network issues

Ensure scraper container is on the same network as Alloy:
```bash
docker run \
  --network imdb-ai-pipeline_internal_network \
  ...
```

## Files Modified

- ✅ `src/scraper_python/pyproject.toml` - Added OTel dependencies
- ✅ `src/scraper_python/src/imdb_top250_scraper/telemetry.py` - New module
- ✅ `src/scraper_python/src/imdb_top250_scraper/logger.py` - Trace injection
- ✅ `src/scraper_python/src/imdb_top250_scraper/cli.py` - Trace initialization
- ✅ `src/scraper_python/src/imdb_top250_scraper/scraper.py` - Span instrumentation

## Next Steps

1. Deploy updated scraper image to production
2. Verify traces appear in Grafana/Tempo
3. Set up alerts based on trace latency/errors
4. Update deployment docs with new environment variables
