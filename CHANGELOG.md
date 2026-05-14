# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-05-14
### 🏗️ Infrastructure & Architecture
- **Changed:** Transitioned the project to a Monorepo structure (`src/`, `infra/`, `docs/`) for better microservice management.
- **Added:** Unified `docker-compose.yml` in the root to orchestrate the entire data pipeline.
- **Added:** Redis message broker integration for high-throughput data ingestion.
- **Added:** Redis Insight container for real-time visual queue monitoring.
- **Added:** PostgreSQL database setup with an auto-executing `init.sql` schema.
- **Added:** Centralized `.env` management for secure credential injection across all containers.

### 🐍 Python Scraper (Producer)
- **Changed:** Deprecated local file I/O. The scraper now acts as a Producer, streaming JSON payloads directly to the Redis `movies_queue`.
- **Added:** `RedisPublisher` class with connection retry logic and logging.
- **Removed:** Legacy CLI arguments related to file output (`--output`, `--format`, `--compact`).
- **Fixed:** Handled Playwright's `TargetClosedError` gracefully during background resource teardown.

### ⚙️ .NET 10 Worker (Consumer)
- **Added:** Brand new C# .NET 10 Background Worker service (`ImdbWorker.Service`).
- **Added:** Real-time queue listening using `StackExchange.Redis` (`ListRightPopAsync` for FIFO processing).
- **Added:** High-performance data storage integration using `Dapper` micro-ORM and `Npgsql`.
- **Added:** SQL UPSERT logic to dynamically insert new movies or update existing ones without conflicts.
- **Added:** Multi-stage `Dockerfile` tailored for .NET 10 Preview, supporting the new experimental `.slnx` solution format.

## [0.1.0] - 2026-05-06
- Added Docker and Docker Compose support.
- Added JSON and JSON Lines output formats.
- Added metadata fields: `scraped_at` and `source_url`.
- Added movie fields: `imdb_id` and `votes_count`.
- Added optional image omission with `--no-images`.
- Added retry, timeout, locale, user-agent, limit, pretty, and compact CLI options.
- Added unit tests, Ruff configuration, Makefile shortcuts, and GitHub Actions CI.
- Added JSON Schema files for JSON output and JSON Lines rows.