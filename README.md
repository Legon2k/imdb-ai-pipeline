# imdb-top250-scraper

Scrapes the IMDb Top 250 chart and saves movie data to JSON.

## Setup

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

For development tools:

```powershell
pip install -r requirements-dev.txt
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

To scrape only the first 10 movies:

```powershell
python imdb_top.py --limit 10
```

To write compact JSON instead of pretty-printed JSON:

```powershell
python imdb_top.py --compact
```

To adjust page timeout, locale, or user agent:

```powershell
python imdb_top.py --timeout 90 --locale en-US --user-agent "Mozilla/5.0 ..."
```

To omit poster image URLs:

```powershell
python imdb_top.py --no-images
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

To omit poster image URLs with Docker:

```powershell
docker run --rm -v "${PWD}/data:/data" imdb-top250-scraper --no-images
```

Or use Docker Compose:

```powershell
docker compose run --rm scraper
```

With Docker Compose and JSON Lines:

```powershell
docker compose run --rm scraper --format jsonl --output /data/custom.jsonl
```

With Docker Compose and no image URLs:

```powershell
docker compose run --rm scraper --no-images
```

With Docker Compose and a limited compact JSON output:

```powershell
docker compose run --rm scraper --limit 10 --compact --output /data/top10.json
```

## Tests

```powershell
python -m unittest discover -s tests
```

## Code Quality

Run Ruff linting:

```powershell
ruff check .
```

Format code:

```powershell
ruff format .
```

## Makefile

If `make` is available, these shortcuts are supported:

```powershell
make install
make install-dev
make install-browser
make test
make lint
make format
make scrape
make docker-build
make docker-run
make compose-run
```

## CI

GitHub Actions runs Ruff, unit tests, and Docker build on push and pull requests.
The CI workflow does not run the real IMDb scrape, so checks stay fast and stable.

## JSON Schema

Schema files are available for downstream validation:

- `schema/imdb_top_250.schema.json` for JSON output
- `schema/imdb_top_250_jsonl_line.schema.json` for each JSON Lines row

## Changelog

See `CHANGELOG.md` for notable project changes.

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
- `imdb_id`
- `title`
- `rating`
- `votes`
- `votes_count`
- `imdb_url`
- `image_url`

`image_url` is omitted when `--no-images` is used.

Example movie record:

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
