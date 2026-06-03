# IMDB AI Pipeline: Enterprise Data Extraction & Enrichment

A high-performance, distributed data pipeline. It scrapes the IMDb Top 250 chart using asynchronous Playwright, streams the data into a Redis message broker, processes it asynchronously using concurrent workers (.NET 10 and a highly efficient Go migration target), and uses a decoupled Python AI Worker to enrich data via Local LLMs (Ollama), all orchestrated by a FastAPI gateway.

## 🏗️ Architecture Overview

This project implements a fully decoupled Event-Driven ETL (Extract, Transform, Load) architecture with isolated Redis Streams, consumer groups, strict Pydantic Data Contracts, and Self-Healing capabilities. It is currently in a migration/coexistence state, supporting both the legacy .NET 10 Worker and the new high-throughput Go Worker.

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