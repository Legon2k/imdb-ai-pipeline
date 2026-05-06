import json
from datetime import UTC, datetime
from pathlib import Path

from imdb_top250_scraper.constants import DEFAULT_OUTPUT_DIR, DEFAULT_OUTPUT_STEM
from imdb_top250_scraper.models import Movie, OutputFormat


def get_default_output_path(output_format: OutputFormat) -> Path:
    return DEFAULT_OUTPUT_DIR / f"{DEFAULT_OUTPUT_STEM}.{output_format}"


def get_scraped_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def format_movies(
    movies: list[Movie],
    output_format: OutputFormat,
    scraped_at: str,
    source_url: str,
    pretty: bool = True,
) -> str:
    if output_format == "json":
        payload = {
            "scraped_at": scraped_at,
            "source_url": source_url,
            "movies": movies,
        }
        indent = 2 if pretty else None
        separators = None if pretty else (",", ":")
        return json.dumps(payload, ensure_ascii=False, indent=indent, separators=separators)

    rows = ({"scraped_at": scraped_at, "source_url": source_url, **movie} for movie in movies)
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"


def write_movies(
    movies: list[Movie],
    output_path: Path,
    output_format: OutputFormat,
    scraped_at: str,
    source_url: str,
    pretty: bool = True,
) -> None:
    output_path.write_text(
        format_movies(movies, output_format, scraped_at, source_url, pretty=pretty),
        encoding="utf-8",
    )
