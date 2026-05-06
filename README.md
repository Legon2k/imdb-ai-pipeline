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

Or use Docker Compose:

```powershell
docker compose run --rm scraper
```

## Tests

```powershell
python -m unittest discover -s tests
```

## Output

Each movie contains:

- `rank`
- `title`
- `rating`
- `votes`
- `votes_count`
- `imdb_url`
- `image_url`
