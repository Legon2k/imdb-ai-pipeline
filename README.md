# IMDB AI Pipeline: Data Ingestion & Processing

A high-performance, distributed data extraction pipeline. It scrapes the IMDb Top 250 chart using asynchronous Playwright, streams the extracted data into a Redis message broker, and processes it asynchronously using a blazing-fast .NET 10 Worker.

## 🏗️ Architecture Overview

This project is built using an Event-Driven ETL (Extract, Transform, Load) architecture:

```mermaid
graph TD
    %% Define Nodes
    Client([Business Client])
    IMDB[IMDB Website]
    Scraper(Python + Playwright<br/>Data Producer)
    Redis[(Redis Queue<br/>Message Broker)]
    Worker(.NET 10 Worker<br/>Data Consumer)
    DB[(PostgreSQL<br/>Persistent Storage)]
    API(FastAPI<br/>API Gateway)
    LLM{{Local LLM<br/>Ollama / Gemma}}

    %% Define Flow
    IMDB -- 1. Scrape DOM --> Scraper
    Scraper -- 2. Push JSON --> Redis
    Redis -- 3. Pop (FIFO) --> Worker
    Worker -- 4. Upsert (Pending) --> DB
    
    Client -- 5. Trigger Enrichment --> API
    API -- 6. Fetch Pending --> DB
    API -- 7. Prompt --> LLM
    LLM -- 8. Return Summary --> API
    API -- 9. Update (Completed) --> DB
    
    Client -- 10. Download .xlsx --> API

    %% Styling
    style Scraper fill:#3776ab,stroke:#fff,stroke-width:2px,color:#fff
    style Redis fill:#dc382d,stroke:#fff,stroke-width:2px,color:#fff
    style Worker fill:#512bd4,stroke:#fff,stroke-width:2px,color:#fff
    style DB fill:#336791,stroke:#fff,stroke-width:2px,color:#fff
    style API fill:#009688,stroke:#fff,stroke-width:2px,color:#fff
    style LLM fill:#f4a261,stroke:#fff,stroke-width:2px,color:#000
```

1. **Scraper (Python + Playwright):** Extracts raw data from the DOM and pushes JSON payloads to Redis.
2. **Message Broker (Redis):** Holds the `movies_queue` to ensure zero data loss.
3. **Background Worker (.NET 10 + Dapper):** Listens to the queue, deserializes payloads, and performs a SQL UPSERT.
4. **Database (PostgreSQL):** Final persistent storage.
5. **API Gateway (FastAPI):** Exposes Swagger UI, orchestrates AI enrichment via local LLM (Ollama), and exports data to `.xlsx`.

## 🚀 Quick Start (Docker Compose)

The easiest way to run the entire infrastructure is using Docker Compose.

**1. Start the Infrastructure & Worker**
```bash
docker compose up -d postgres redis redis-insight worker
```
*Wait a few seconds for the databases to initialize and the .NET worker to start listening to the queue.*

**2. Monitor the Queue (UI)**
Open your browser and navigate to **[http://localhost:5540](http://localhost:5540)** (Redis Insight). Connect to the `imdb_redis` host on port `6379` to monitor the data flow in real-time.

**3. Run the Scraper (Data Ingestion)**
Start the extraction process:
```bash
docker compose start scraper
```
The scraper will launch a headless Chromium instance, scrape the movies, push them to the Redis `movies_queue`, and gracefully exit. The `.NET worker` will instantly pick up the payloads and save them to PostgreSQL.

**4. Verify Data in PostgreSQL**
To see the processed results directly in the database:
```bash
docker exec -it imdb_postgres psql -U imdb_admin -d imdb_ai_db -c "SELECT rank, title, rating, status FROM movies ORDER BY rank LIMIT 10;"
```

## 💻 Local Development (Python Scraper)

If you want to run the scraper outside of Docker, ensure your virtual environment is set up and the infrastructure is running.

```powershell
pip install -r src/scraper_python/requirements.txt
python -m playwright install chromium

python src/scraper_python/src/imdb_top.py --limit 10
```

### Supported CLI Arguments

- `--limit 10`: Scrape only a specific number of movies.
- `--retries 5 --log-level DEBUG`: Retry failed scrapes and adjust verbosity.
- `--timeout 90 --locale en-US --user-agent "Mozilla/5.0 ..."`: Adjust page timeout, locale, or user agent.
- `--no-images`: Omit poster image URLs to save bandwidth.

## 📦 Message Payload Format (Redis)

The scraper publishes a JSON object to the `movies_queue` list in Redis for each extracted movie. The .NET Worker deserializes this payload and saves it to PostgreSQL.

```json
{
  "rank": 1,
  "imdb_id": "tt0111161",
  "title": "The Shawshank Redemption",
  "imdb_url": "https://www.imdb.com/title/tt0111161/?ref_=chttp_t_1",
  "image_url": "https://m.media-amazon.com/images/...",
  "rating": 9.3,
  "votes": "3.2M",
  "votes_count": 3200000
}
```

## 🧪 Tests & Code Quality

Run Python tests:
```powershell
python -m unittest discover -s src/scraper_python/tests
```

Run Ruff linting and formatting:
```powershell
ruff check .
ruff format .
```

## 📈 CI / CD

GitHub Actions automatically runs Ruff, unit tests, and Docker builds on push and pull requests to ensure code quality.

## 🗺️ Diagrams

System architecture diagrams can be found in `docs/architecture.drawio` and can be edited using [Draw.io](https://www.drawio.com/).