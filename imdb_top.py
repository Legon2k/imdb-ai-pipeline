import argparse
import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from playwright.async_api import Browser, Page, Route, async_playwright

IMDB_TOP_URL = "https://www.imdb.com/chart/top/"
MOVIE_SELECTOR = ".ipc-metadata-list-summary-item"
EXPECTED_MOVIE_COUNT = 250
DEFAULT_OUTPUT_DIR = Path(__file__).with_name("data")
DEFAULT_OUTPUT_STEM = "imdb_top_250"
DEFAULT_RETRIES = 3
OutputFormat = Literal["json", "jsonl"]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
LOGGER = logging.getLogger(__name__)


async def block_heavy_resources(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font"}:
        await route.abort()
    else:
        await route.continue_()


def parse_rating(raw_rating: str) -> tuple[float | None, str | None, int | None]:
    cleaned = " ".join(raw_rating.split()).replace("\xa0", " ")
    match = re.search(r"(?P<rating>\d+(?:\.\d+)?)\s*(?:\((?P<votes>[^)]+)\))?", cleaned)

    if not match:
        return None, None, None

    votes = match.group("votes")
    return float(match.group("rating")), votes, parse_votes_count(votes)


def parse_votes_count(raw_votes: str | None) -> int | None:
    if not raw_votes:
        return None

    cleaned = raw_votes.strip().replace(",", "").upper()
    match = re.fullmatch(r"(?P<number>\d+(?:\.\d+)?)(?P<suffix>[KMB])?", cleaned)
    if not match:
        return None

    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    multiplier = multipliers.get(match.group("suffix"), 1)
    return int(float(match.group("number")) * multiplier)


def extract_imdb_id(imdb_url: str | None) -> str | None:
    if not imdb_url:
        return None

    match = re.search(r"/title/(?P<imdb_id>tt\d+)/?", imdb_url)
    if not match:
        return None

    return match.group("imdb_id")


async def extract_movies(page: Page) -> list[dict]:
    movies = page.locator(MOVIE_SELECTOR)

    raw_movies = await movies.evaluate_all(
        """
        items => items.map((item, index) => {
            const titleText = item.querySelector(".ipc-title__text")?.textContent?.trim() || "";
            const ratingText = (
                item.querySelector("span[aria-label*='IMDb rating']") ||
                item.querySelector("span[aria-label*='rating']")
            )?.textContent?.trim() || "";
            const link = item.querySelector("a.ipc-title-link-wrapper")?.href || null;
            const image = item.querySelector("img")?.src || null;

            return {
                rank: index + 1,
                title: titleText.replace(/^\\d+\\.\\s*/, ""),
                rating_text: ratingText,
                imdb_url: link,
                image_url: image
            };
        })
        """
    )

    results = []
    for movie in raw_movies:
        rating, votes, votes_count = parse_rating(movie.pop("rating_text"))
        movie["imdb_id"] = extract_imdb_id(movie.get("imdb_url"))
        movie["rating"] = rating
        movie["votes"] = votes
        movie["votes_count"] = votes_count
        results.append(movie)

    return results


async def scrape_imdb_top_250(
    output_path: Path,
    output_format: OutputFormat = "json",
    retries: int = DEFAULT_RETRIES,
) -> list[dict]:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            LOGGER.info("Scraping IMDb Top 250, attempt %s of %s", attempt, retries)
            return await scrape_once(output_path, output_format)
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break

            LOGGER.warning("Scrape attempt %s failed: %s", attempt, exc)
            await asyncio.sleep(attempt)

    raise RuntimeError(f"Failed to scrape IMDb Top 250 after {retries} attempts.") from last_error


async def scrape_once(output_path: Path, output_format: OutputFormat) -> list[dict]:
    browser: Browser | None = None

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale="en-US",
                user_agent=USER_AGENT,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await context.new_page()
            await page.route("**/*", block_heavy_resources)

            await page.goto(IMDB_TOP_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_selector(MOVIE_SELECTOR, timeout=30_000)
            movie_count_expression = (
                f"() => document.querySelectorAll('{MOVIE_SELECTOR}').length "
                f">= {EXPECTED_MOVIE_COUNT}"
            )
            await page.wait_for_function(
                movie_count_expression,
                timeout=30_000,
            )

            results = await extract_movies(page)
            if len(results) < EXPECTED_MOVIE_COUNT:
                raise RuntimeError(f"Expected {EXPECTED_MOVIE_COUNT} movies, got {len(results)}.")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_movies(
                results,
                output_path,
                output_format,
                scraped_at=get_scraped_at(),
                source_url=IMDB_TOP_URL,
            )

            return results
        finally:
            if browser is not None:
                await browser.close()


def get_default_output_path(output_format: OutputFormat) -> Path:
    return DEFAULT_OUTPUT_DIR / f"{DEFAULT_OUTPUT_STEM}.{output_format}"


def get_scraped_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def format_movies(
    movies: list[dict],
    output_format: OutputFormat,
    scraped_at: str,
    source_url: str,
) -> str:
    if output_format == "json":
        payload = {
            "scraped_at": scraped_at,
            "source_url": source_url,
            "movies": movies,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    rows = ({"scraped_at": scraped_at, "source_url": source_url, **movie} for movie in movies)
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"


def write_movies(
    movies: list[dict],
    output_path: Path,
    output_format: OutputFormat,
    scraped_at: str,
    source_url: str,
) -> None:
    output_path.write_text(
        format_movies(movies, output_format, scraped_at, source_url),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape IMDb Top 250 movies to JSON.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file path. Default: data/imdb_top_250.<format>",
    )
    parser.add_argument(
        "--format",
        choices=["json", "jsonl"],
        default="json",
        help="Output format. Default: json",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Number of scrape attempts. Default: {DEFAULT_RETRIES}",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity. Default: INFO",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(message)s")
    output_path = args.output or get_default_output_path(args.format)
    movies = await scrape_imdb_top_250(
        output_path,
        output_format=args.format,
        retries=args.retries,
    )
    LOGGER.info("Saved %s movies to %s", len(movies), output_path)


if __name__ == "__main__":
    asyncio.run(main())
