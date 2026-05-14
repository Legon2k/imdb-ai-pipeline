# IMDB AI Pipeline: Data Ingestion Layer

A high-performance, distributed data extraction pipeline. It scrapes the IMDb Top 250 chart using asynchronous Playwright and instantly streams the extracted movie data into a Redis message broker for downstream processing.

## 🏗️ Architecture Overview

This project is part of a larger microservice architecture:
1. **Scraper (Python + Playwright):** Acts as a Producer. Extracts data from the DOM and pushes JSON payloads to Redis.
2. **Message Broker (Redis):** Holds the `movies_queue` to ensure zero data loss.
3. **Database (PostgreSQL):** Final persistent storage for the movies and future AI-generated summaries.

## 🚀 Quick Start (Docker Compose)

The easiest way to run the entire infrastructure is using Docker Compose.

**1. Start the Infrastructure (Databases & UI)**
```bash
docker compose up -d postgres redis redis-insight
```
*Wait a few seconds for the databases to initialize and become healthy.*

**2. Monitor the Queue (UI)**
Open your browser and navigate to **[http://localhost:5540](http://localhost:5540)** (Redis Insight). Connect to the `imdb_redis` host on port `6379` to monitor the data flow in real-time.

**3. Run the Scraper**
Start the ingestion process:
```bash
docker compose up scraper
```
The scraper will launch a headless Chromium instance, scrape the movies, push them to the Redis `movies_queue`, and gracefully exit.

## 💻 Local Development (Python)

If you want to run the scraper outside of Docker, ensure your virtual environment is set up and the infrastructure (Redis) is running.

```powershell
# Install dependencies
pip install -r src/scraper_python/requirements.txt
python -m playwright install chromium

# Run the scraper
python src/scraper_python/src/imdb_top.py
```

### Supported CLI Arguments

The scraper supports various configuration flags:

To retry failed scrapes or change logging verbosity:
```powershell
python src/scraper_python/src/imdb_top.py --retries 5 --log-level DEBUG
```

To scrape only a specific number of movies (useful for testing):
```powershell
python src/scraper_python/src/imdb_top.py --limit 10
```

To adjust page timeout, locale, or user agent:
```powershell
python src/scraper_python/src/imdb_top.py --timeout 90 --locale en-US --user-agent "Mozilla/5.0 ..."
```

To omit poster image URLs to save bandwidth:
```powershell
python src/scraper_python/src/imdb_top.py --no-images
```

*(Note: File output arguments like `--output` and `--format` have been deprecated in favor of the Redis message broker).*

## 📦 Message Payload Format (Redis)

Instead of saving to a local JSON file, the scraper publishes a JSON object to the `movies_queue` list in Redis for each extracted movie.

Example of a single message payload:

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

Run tests:
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