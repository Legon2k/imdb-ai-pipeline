# ADR-002: Add Prometheus-Based Worker Observability

## Status
Accepted

## Date
June 2026

## Context
The IMDb AI Pipeline is an event-driven system with independent services consuming Redis Streams and writing to PostgreSQL. As the pipeline grows beyond a single worker implementation, operational visibility must cover both business outcomes and runtime behavior across service boundaries.

Before this decision, worker behavior was primarily observable through logs. Logs are useful for diagnostics, but they are not enough for fast operational feedback on throughput, validation failures, database write failures, local LLM latency, or AI enrichment quality signals such as generated summary size.

The pipeline needs a Cloud-Native metrics approach that:

1. Exposes service-local runtime metrics without writing local files.
2. Works naturally in containers and Compose-managed networks.
3. Supports future dashboards and alerting without changing worker business logic.
4. Provides stable metric names for worker outcome tracking and latency analysis.

## Alternatives Considered

### Alternative 1: Continue with Logs Only
* **Pros**: No new infrastructure component or dependency required.
* **Cons**: Logs are harder to aggregate into time-series views, less suitable for alerting on rates/latency, and require query-specific parsing for operational dashboards.

### Alternative 2: Push Metrics to an External Gateway
* **Pros**: Can be useful for short-lived batch jobs or environments where pull scraping is not possible.
* **Cons**: Adds another runtime dependency and is unnecessary for long-running workers that can expose HTTP metrics endpoints directly.

### Alternative 3: Use Prometheus Pull-Based Scraping
* **Pros**: Standard Cloud-Native approach, simple container integration, broad ecosystem support, and mature client libraries for Python and Go.
* **Cons**: Requires exposing metrics ports and running a Prometheus service in local/infrastructure environments.

---

## Decision
Adopt **Prometheus pull-based metrics** for worker observability.

The Python AI Worker exposes Prometheus metrics on port `8001`, and the Go Movie Worker exposes metrics on port `2112`. A Prometheus service is added to `docker-compose.yml` and configured through `infra/prometheus/prometheus.yml` to scrape both workers on the internal Compose network.

The following application metrics are part of the worker observability contract:

* `ai_tasks_processed_total`: AI worker task outcomes by `status`.
* `llm_request_duration_seconds`: local LLM generation latency.
* `llm_summary_characters`: character length of successful LLM summaries.
* `movies_processed_total`: Go worker movie processing outcomes by `status`.

---

## Consequences

### Positive (Benefits)
1. **Operational Visibility**: Worker success, validation failures, database failures, LLM latency, and summary sizes can be monitored as time-series metrics.
2. **Cloud-Native Runtime Model**: Metrics are exposed through HTTP endpoints and scraped by Prometheus, avoiding local filesystem dependencies.
3. **Dashboard and Alerting Foundation**: The pipeline now has stable metric names that can be used by future Grafana dashboards and Prometheus alert rules.
4. **Language-Native Instrumentation**: Python and Go workers use standard Prometheus client libraries for idiomatic instrumentation.

### Negative / Neutral (Drawbacks)
1. **Additional Service**: Local and containerized environments now include a Prometheus service.
2. **Additional Ports**: Worker metrics ports `8001` and `2112`, plus Prometheus UI port `9090`, must be accounted for in local development and deployment environments.
3. **Metric Contract Maintenance**: Metric names and labels should remain stable to avoid breaking dashboards and alerts.

---

## Technical Details

* **Metrics Backend**: Prometheus (`prom/prometheus:latest`).
* **Prometheus Configuration**: `infra/prometheus/prometheus.yml`.
* **Python Client**: `prometheus-client`.
* **Go Client**: `github.com/prometheus/client_golang/prometheus` and `github.com/prometheus/client_golang/prometheus/promhttp`.
* **Python AI Worker Metrics Endpoint**: `http://localhost:8001/metrics`.
* **Go Movie Worker Metrics Endpoint**: `http://localhost:2112/metrics`.
* **Prometheus Web UI**: `http://localhost:9090`.
