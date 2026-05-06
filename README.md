# imdb-top250-scrape

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

By default, the script writes `imdb_top_250.json` next to `imdb_top.py`.

To choose another output file:

```powershell
python imdb_top.py --output data/imdb_top_250.json
```

## Docker

Build the image:

```powershell
docker build -t imdb-top250-scrape .
```

Run the scraper and save the result to `data/imdb_top_250.json` on your machine:

```powershell
New-Item -ItemType Directory -Force data
docker run --rm -v "${PWD}/data:/data" imdb-top250-scrape
```

To choose another output file inside the mounted `/data` directory:

```powershell
docker run --rm -v "${PWD}/data:/data" imdb-top250-scrape --output /data/custom.json
```

## Output

Each movie contains:

- `rank`
- `title`
- `rating`
- `votes`
- `imdb_url`
- `image_url`
