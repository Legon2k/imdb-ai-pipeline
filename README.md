# IMDB AI Pipeline: Enterprise Data Extraction & Enrichment

A high-performance, distributed data pipeline. It scrapes the IMDb Top 250 chart using asynchronous Playwright, streams the data into a Redis message broker, processes it asynchronously using concurrent workers, and uses a decoupled Python AI Worker to enrich data via Local LLMs (Ollama), all orchestrated by a FastAPI gateway.

## 🏗️ Architecture Overview

This project implements a fully decoupled Event-Driven ETL (Extract, Transform, Load) architecture with isolated Redis Streams, consumer groups, strict Pydantic Data Contracts, and Self-Healing capabilities. It is currently in a migration/coexistence state: the legacy .NET 10 Worker remains the reference ingestion service, while `worker_go` has been added as the Go-based transit implementation that will be tested side by side before the final cutover.

```mermaid
graph TD
    %% Define Nodes
    Client([Business Client])
    IMDB[IMDB Website]
    Scraper(Python + Playwright<br/>Data Producer)
    RedisMovies[(Redis Stream<br/>'movies_stream')]
    WorkerNET(.NET 10 Worker<br/>Legacy Consumer)
    WorkerGo(Go Movie Worker<br/>Migration Target)
    DB[(PostgreSQL<br/>Persistent Storage)]
    API(FastAPI<br/>API Gateway)
    RedisAI[(Redis Stream<br/>'ai_stream')]
    WorkerAI(Python AI Worker<br/>LLM Consumer)
    LLM{{Local LLM<br/>Ollama / Gemma}}

    %% Define Flow
    IMDB -- 1. Scrape DOM --> Scraper
    Scraper -- 2. XADD payload --> RedisMovies
    RedisMovies -- 3. XREADGROUP --> WorkerNET
    RedisMovies -- 3. XREADGROUP --> WorkerGo
    WorkerNET -- 4. Upsert + XACK --> DB
    WorkerGo -- 4. Upsert + XACK --> DB
    
    Client -- 5. Trigger Enrichment --> API
    API -- 6. Lock Pending<br/>SKIP LOCKED --> DB
    API -- 7. XADD Tasks --> RedisAI
    RedisAI -- 9. XREADGROUP --> WorkerAI
    WorkerAI -- 10. Prompt --> LLM
    LLM -- 11. Summary --> WorkerAI
    WorkerAI -- 12. Update + XACK --> DB
    
    Client -- 13. Download .xlsx --> API

    %% Styling
    style Scraper fill:#3776ab,stroke:#fff,stroke-width:2px,color:#fff
    style RedisMovies fill:#dc382d,stroke:#fff,stroke-width:2px,color:#fff
    style RedisAI fill:#dc382d,stroke:#fff,stroke-width:2px,color:#fff
    style WorkerNET fill:#512bd4,stroke:#fff,stroke-width:2px,color:#fff
    style WorkerGo fill:#00add8,stroke:#fff,stroke-width:2px,color:#fff
    style DB fill:#336791,stroke:#fff,stroke-width:2px,color:#fff
    style API fill:#009688,stroke:#fff,stroke-width:2px,color:#fff
    style WorkerAI fill:#f6d04d,stroke:#fff,stroke-width:2px,color:#000
    style LLM fill:#f4a261,stroke:#fff,stroke-width:2px,color:#000
```

## Worker Migration: .NET to Go

The movie ingestion layer is intentionally running in a transition mode according to [ADR-001](docs/adr/001-migration-from-dotnet-to-go-worker.md).

- `src/worker_dotnet` / `worker`: current .NET 10 Worker and baseline implementation.
- `src/worker_go` / `worker_go`: Golang Worker added for transit and future replacement of the .NET service.
- Both workers consume `movies_stream` through Redis consumer groups and persist normalized movie data into PostgreSQL.
- The next phase is comparative testing of both services and collecting the final migration results.
- After the test results are accepted, the pipeline will be switched fully to `worker_go`; the .NET worker can then be removed or kept only as a rollback reference.

The rationale, alternatives, and expected operational impact are documented in ADR-001.
