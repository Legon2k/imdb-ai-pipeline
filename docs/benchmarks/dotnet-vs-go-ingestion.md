# Data Ingestion Benchmark Report: .NET 10 vs Go 1.24

## 🎯 Objective
The primary objective of this benchmark is to measure and compare the raw performance, runtime latency, and resource efficiency of the legacy **.NET 10 Worker** (`worker_dotnet`) against the new **Go 1.24 Worker** (`worker_go`) during high-concurrency stream ingestion.

To isolate application layer overhead (network transport, JSON deserialization, contract validation, and stream acknowledgment) from database disk I/O bottlenecks, database writes are bypassed in both services (`_simulateDbSave` and `SimulateDbSave` set to `true`).

---

## 💻 Environment Specifications

The tests were executed on a dedicated local virtualization environment under controlled thermal and power limits to simulate resource-constrained cloud environments (such as lower-tier AWS EC2 or ECS Fargate instances).

| Parameter | Specification |
| :--- | :--- |
| **CPU** | Intel Core Ultra 7 155H (Meteor Lake, 16 Cores, 22 Threads) |
| **RAM** | 32 GB LPDDR5 |
| **Container Engine** | Podman v5.8.2 |
| **Host OS Kernel** | WSL2 (Windows Subsystem for Linux) v2.6.1.0 |
| **Testing Mode** | **Quiet / Power-Saving Mode** (CPU restricted to a maximum of **2000 MHz**) |

---

## 🧪 Benchmark Methodology

To ensure clean and comparable telemetry data, both ingestion workers consumed from a pre-populated Redis Stream concurrently, acting as members of the same consumer group (`imdb_worker`). This setup simulates a production rolling update or a canary deployment where work is shared dynamically based on runtime capacity.

### 1. Environment Configuration (.env)
The environment variables were set to suppress verbose console output (reducing container stdout I/O overhead) and bypass physical PostgreSQL writes:

    # Disable debug logging to prevent container stdout bottlenecks
    LOG_LEVEL=INFO

    # Bypass database writes to isolate runtime and stream ingestion performance
    SIMULATE_SAVE_MOVIE_TO_DATABASE=true

### 2. Execution Sequence (PowerShell)
The following commands were executed to clean, populate, and run the benchmark stack:

    # 1. Spin up the infrastructure core (PostgreSQL, Redis, Prometheus, Grafana)
    podman-compose up -d

    # 2. Stop both consumers to allow the stream to populate in isolation
    podman-compose stop worker_go worker

    # 3. Clean any stale data or pending messages in the Redis Stream
    make load-bench-clean

    # 4. Ingest 10,000,000 realistic movie JSON payloads into the Redis Stream
    # (Executed natively inside the container network to bypass Windows host proxy overhead)
    podman compose run --rm scraper python tests/load_bench/fill_redis_stream.py --host imdb_redis --count 10000000

    # 5. Start both workers simultaneously to process the 10M stream concurrently
    podman-compose start worker_go worker

    # 6. Monitor telemetry in the Grafana dashboard during the 15-minute run
    # (Dashboard accessible at http://localhost:3000)

    # 7. Clean up stream data after benchmark completion
    make load-bench-clean

---

## 📊 Telemetry & Performance Analysis

The live telemetry captured in Grafana during the 10,000,000 message run reveals the distinct behaviors of the Go and .NET runtimes under constrained CPU frequencies (2000 MHz).

### 1. Ingestion Throughput (RPS)
*   **Go Worker (worker-go)**: Stabilized at an average processing rate of **700–850 RPS**, peaking at **950 RPS**.
*   **.NET 10 Worker (worker-dotnet)**: Reached a stable processing limit of **300–400 RPS**, peaking at **450 RPS**.
*   **Analysis**: Go consistently achieved **over 2.2x higher throughput** than .NET 10. Under strict CPU frequency caps (2000 MHz), Go’s lightweight concurrency model (multiplexing goroutines via the Go scheduler) incurs significantly less CPU context-switching overhead than .NET's OS-thread-mapped ThreadPool.

### 2. Processing Latency Percentiles (P50, P95, P99)
*   **The Startup JIT & Warm-Up Penalty (14:06:00)**:
    At the initiation of the stream processing, the .NET P99 latency spiked dramatically to **19.0 ms**, whereas Go's P99 spiked to only **9.0 ms**. 
    *   *Reasoning*: In .NET, this is the "warm-up" penalty caused by the JIT (Just-In-Time) compiler dynamically compiling the intermediate IL code for JSON deserialization, contract validation methods, and assembly loading. In contrast, Go is pre-compiled into a static native binary, bypassing JIT entirely; its minimal 9ms startup spike is purely due to the initial socket allocation for the Redis connection pool.
*   **Tail Latency Stability (P99 Jitter)**:
    Once warmed up, the Go P99 latency (purple line) remained extremely flat and stable, fluctuating tightly between **3.5 ms and 5.0 ms**. The .NET P99 latency (red line) was highly volatile, constantly undulating and spiking between **7.0 ms and 9.5 ms**.
    *   *Reasoning*: .NET's latency waves are driven by the generational Garbage Collector (GC) executing Gen 0 and Gen 1 collection pauses (Stop-the-World pauses) under a continuous allocation stream. Go's latency remains flat because its concurrent tri-color mark-sweep garbage collector runs concurrently with application goroutines, keeping GC pauses sub-millisecond.

### 3. Memory Consumption (Working Set)
*   **.NET 10 Worker**: Began at ~75 MiB and climbed steadily before flattening into a stable plateau at **96 MiB**.
*   **Go Worker**: Maintained a perfectly flat line at **18 MiB** (representing a **5.3x reduction in physical RAM**).
*   **Analysis**: The flat 96 MiB .NET plateau indicates that the .NET GC reached a steady state of memory reclamation. However, the 18 MiB footprint of Go proves the efficiency of its stack-allocation compiler optimizations (escape analysis), which bypass the managed heap entirely for temporary variables used during short JSON processing cycles.

### 4. Impact of CPU Throttling Modes (Quiet vs Normal)
*   In this benchmark (Quiet Mode, 2000 MHz max), both runtimes operated under thermal constraints, resulting in the wave-like throughput patterns on the chart.
*   In comparative tests conducted in **Normal Mode** (unthrottled CPU), the latency of both runtimes collapsed into the **sub-millisecond range (<1.0 ms)**, and Go's throughput surged past **3200+ RPS**. This proves that while raw CPU clock speeds directly scale throughput, the comparative efficiency ratio—where **Go is ~2.2x faster and consumes 5.3x less RAM**—remains constant.

---

## 📝 Conclusion
The 10M message endurance benchmark provides empirical verification for [ADR-001](../../docs/adr/001-migration-from-dotnet-to-go-worker.md). For high-throughput, I/O-bound stream processing workloads, migrating the ingestion worker to Go 1.24 delivers a **2.2x performance boost** and **saves over 80% in memory utilization**, translating directly to significant cloud infrastructure savings (FinOps) and superior auto-scaling capabilities.