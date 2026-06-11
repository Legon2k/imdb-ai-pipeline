# ADR-001: Migration of Data Ingestion Worker from .NET 10 to Go (Golang)

## Status
Accepted

## Date
June 2026

## Context
The initial implementation of the movie data ingestion worker (`worker_dotnet`) was built using .NET 10. While .NET 10 provides a modern runtime, it carries significant overhead that impacts operational costs as the pipeline transitions to cloud environments (e.g., AWS ECS Fargate / Kubernetes).

Key operational challenges identified with the .NET 10 implementation include:
1. **Memory Footprint**: The Common Language Runtime (CLR) and Just-In-Time (JIT) compiler require approximately 120MB–180MB of RAM under load for a relatively simple I/O-bound stream consumer.
2. **Container Image Size**: The minimal .NET Alpine runtime image is ~180MB, which increases deployment times, storage costs, and security scan attack surfaces in CI/CD pipelines.
3. **Cold Start Latency**: Runtime initialization takes several seconds, restricting the system's ability to scale rapidly in response to sudden stream spikes.

To optimize cloud infrastructure spend (Cloud FinOps) and transition to a highly modular, Cloud-Native architecture, we need to minimize resource utilization without sacrificing processing throughput.

## Alternatives Considered

### Alternative 1: Retain the .NET 10 Worker
* **Pros**: No rewrite required; utilizes existing C# code and Dapper integration.
* **Cons**: High operational cost overhead (RAM and container size) in serverless/containerized cloud environments.

### Alternative 2: Rewrite in Rust
* **Pros**: Extremely low resource usage, zero garbage collection pauses, and maximal performance.
* **Cons**: Steeper learning curve, increased development complexity, and slower delivery speed for a pipeline dominated by network I/O.

---

## Decision
Migrate the data ingestion worker (`worker_dotnet`) to **Go (Golang) 1.24** (`worker_go`). 

Go compiled binaries represent a highly optimal balance of rapid development speed, native concurrency primitives, and minimal resource footprints, making them ideal for high-throughput stream processing.

---

## Consequences

### Positive (Benefits)
1. **Drastic Resource Reduction**: Memory utilization is reduced from ~150MB to **~10-15MB** under active stream processing (over 90% savings). This allows for much denser container packing on cloud nodes.
2. **Minimalist Image Footprint**: The Go statically-linked binary compiled inside an Alpine container reduces the image size from ~180MB to **~25MB**.
3. **Rapid Startup**: Native execution drops cold-start times to milliseconds, enabling fast auto-scaling.
4. **Idiomatic Concurrency**: Go's native goroutines and channel model provide efficient execution for concurrent worker pools with negligible system thread context-switching.
5. **No Runtime Dependencies**: The output is a single, self-contained binary, simplifying security scanning and reducing potential CVE vulnerabilities.
6. **Experimental Validation**: The decision is backed by solid empirical data from a 10M message load test. Go demonstrated a 2.5x throughput gain, 5.5x memory reduction, and 50x faster cold starts. See the complete telemetry in the [Data Ingestion Benchmark Report](../benchmarks/dotnet-vs-go-ingestion.md).

### Negative / Neutral (Drawbacks)
1. **Migration Effort**: Requires rewriting the existing .NET consumer logic, JSON validation, and Postgres UPSERT queries in Go.
2. **Language Split**: Adds Go to a previously .NET/Python-heavy monorepository, slightly increasing the technology stack breadth (mitigated by Go's simplicity and clean tooling).

---

## Technical Details

* **Language**: Go 1.24
* **Driver (Postgres)**: `github.com/jackc/pgx/v5` (for high-performance binary protocol protocol and built-in connection pooling).
* **Driver (Redis)**: `github.com/redis/go-redis/v9` (official client for stream consumer groups).
* **Configuration**: `github.com/caarlos0/env/v11` (type-safe environment parsing).
* **Logging**: Structured JSON logging using standard library `log/slog`.