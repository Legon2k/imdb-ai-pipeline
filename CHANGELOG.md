# Changelog

All notable changes to this project will be documented in this file.

## [0.6.0] - 2026-05-16
### Reliability Hardening
- **Added:** FastAPI liveness and readiness endpoints: `GET /health` and `GET /ready`.
- **Added:** API smoke tests for enrichment locking, Redis Stream publishing, and rollback on publish failure.
- **Added:** Configurable approximate Redis Stream retention via `MOVIES_STREAM_MAXLEN` and `AI_STREAM_MAXLEN`.
- **Changed:** Replaced Redis List queue operations with Redis Streams consumer groups for movie ingestion and AI enrichment tasks.
- **Changed:** `POST /movies/enrich` now locks pending rows with PostgreSQL `FOR UPDATE SKIP LOCKED` before queueing AI tasks, preventing duplicate queueing during overlapping enrichment requests.
- **Fixed:** `POST /movies/recover` now uses a parameterized interval query and validates `stuck_minutes`.
- **Fixed:** AI Worker task recovery no longer relies on `locals()`, preventing an older task from being reverted after an unrelated failure.
- **Added:** Configurable `LLM_TIMEOUT_SECONDS` to bound local LLM requests and avoid indefinite hangs.
- **Removed:** Legacy scraper JSON/JSONL output module, schema files, and output-format tests after the pipeline moved to Redis-based ingestion.

## [0.5.0] - 2026-05-16
### 🛡️ Resilience & Self-Healing (Fault Tolerance)
- **Added:** Implemented a "Self-Healing" mechanism to resolve the "Zombie Task" problem in distributed systems.
- **Added:** `POST /movies/recover` API endpoint. It scans PostgreSQL for tasks stuck in the `processing` state due to worker crashes or timeouts and safely reverts them to `pending`.
- **Added:** AI Worker safeguard block. If the local LLM fails or times out, the worker catches the exception and automatically reverts the database lock back to `pending` to allow future retries.

## [0.4.0] - 2026-05-16
### 📦 Data Integrity & Contracts
- **Added:** Implemented strict JSON Data Contracts across microservices using `Pydantic`.
- **Changed:** FastAPI endpoints now utilize `response_model` schemas, automatically generating strongly-typed Swagger UI documentation for frontend/client integration.
- **Added:** AI Worker now validates incoming Redis payloads against the `AITaskContract` schema, catching `ValidationError` exceptions to prevent processing corrupt tasks (Safeguard pattern).

## [0.3.0] - 2026-05-15
### 🏗️ Infrastructure & Architecture
- **Changed:** Upgraded system architecture to fully decoupled asynchronous task queues for LLM processing.
- **Changed:** Updated `docker-compose.yml` to include the new `api` and `worker_ai` microservices.
- **Fixed:** Resolved Docker container log buffering issues by enforcing `PYTHONUNBUFFERED=1` across all Python containers for real-time observability.
- **Added:** Updated Mermaid.js architecture diagram in `README.md` to reflect the new AI-consumer pattern.

### 🌐 FastAPI Gateway
- **Added:** Brand new `api_fastapi` microservice to act as the primary data delivery layer.
- **Added:** Auto-generated Swagger UI documentation for easy client testing.
- **Added:** `GET /movies/export` endpoint utilizing `pandas` and `openpyxl` to generate formatted Excel (`.xlsx`) reports on the fly.
- **Added:** `POST /movies/enrich` asynchronous endpoint. It fetches `pending` movies and pushes task payloads to the Redis `ai_queue`, returning an instant `HTTP 202 Accepted` to prevent gateway timeouts.

### 🤖 AI Worker
- **Added:** Dedicated `worker_ai_python` background service.
- **Added:** Redis `BRPOP` consumer logic to process AI generation tasks one-by-one, preventing VRAM Out-Of-Memory (OOM) errors on the host machine.
- **Added:** Seamless integration with Local LLMs (Ollama / `gemma4:e4b`) using asynchronous HTTP requests (`httpx`).
- **Added:** PostgreSQL updates to transition movie statuses from `pending` -> `processing` -> `completed` after successful AI enrichment.

## [0.2.0] - 2026-05-14
### 🏗️ Infrastructure & Architecture
- **Changed:** Transitioned the project to a Monorepo structure (`src/`, `infra/`, `docs/`).
- **Added:** Unified `docker-compose.yml` in the root.
- **Added:** Redis message broker integration for high-throughput data ingestion.
- **Added:** Redis Insight container for real-time visual queue monitoring.
- **Added:** PostgreSQL database setup with an auto-executing `init.sql` schema.

### 🐍 Python Scraper (Producer)
- **Changed:** Deprecated local file I/O. The scraper now acts as a Producer, streaming JSON payloads directly to Redis.
- **Added:** `RedisPublisher` class with connection retry logic.

### ⚙️ .NET 10 Worker (Consumer)
- **Added:** Brand new C# .NET 10 Background Worker service (`ImdbWorker.Service`).
- **Added:** High-performance data storage integration using `Dapper` micro-ORM and `Npgsql`.
- **Added:** SQL UPSERT logic.

## [0.1.0] - 2026-05-06
- Initial release with synchronous scraping script and Docker support.
