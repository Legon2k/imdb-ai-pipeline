# imdb-top250-scraper

Scrapes the IMDb Top 250 chart and saves movie data to JSON.

## Setup

```powershell
pip install playwright
python -m playwright install chromium
```

## Usage

```powershell
python imdb_top.py
```

By default, the script writes `data/imdb_top_250.json`.

To choose another output file:

```powershell
python imdb_top.py --output data/imdb_top_250.json
```

To write JSON Lines instead of a JSON array:

```powershell
python imdb_top.py --format jsonl
```

This writes `data/imdb_top_250.jsonl` by default. You can also choose the file name:

```powershell
python imdb_top.py --format jsonl --output data/imdb_top_250.jsonl
```

To retry failed scrapes or change logging verbosity:

```powershell
python imdb_top.py --retries 5 --log-level DEBUG
```

## Docker

Build the image:

```powershell
docker build -t imdb-top250-scraper .
```

Run the scraper and save the result to `data/imdb_top_250.json` on your machine:

```powershell
New-Item -ItemType Directory -Force data
docker run --rm -v "${PWD}/data:/data" imdb-top250-scraper
```

To choose another output file inside the mounted `/data` directory:

```powershell
docker run --rm -v "${PWD}/data:/data" imdb-top250-scraper --output /data/custom.json
```

To write JSON Lines with Docker:

```powershell
docker run --rm -v "${PWD}/data:/data" imdb-top250-scraper --format jsonl --output /data/custom.jsonl
```

Or use Docker Compose:

```powershell
docker compose run --rm scraper
```

With Docker Compose and JSON Lines:

```powershell
docker compose run --rm scraper --format jsonl --output /data/custom.jsonl
```

## Tests

```powershell
python -m unittest discover -s tests
```

## Output

JSON output is an object with metadata and a `movies` array:

```json
{
  "scraped_at": "2026-05-06T12:00:00Z",
  "source_url": "https://www.imdb.com/chart/top/",
  "movies": []
}
```

JSON Lines output writes one movie object per line. Each line includes `scraped_at`
and `source_url`.

Each movie contains:

- `rank`
- `title`
- `rating`
- `votes`
- `votes_count`
- `imdb_url`
- `image_url`
