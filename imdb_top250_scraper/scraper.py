import asyncio
import logging
from pathlib import Path

from playwright.async_api import Browser, Page, Route, async_playwright

from imdb_top250_scraper.constants import (
    DEFAULT_LOCALE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    EXPECTED_MOVIE_COUNT,
    IMDB_TOP_URL,
    MOVIE_SELECTOR,
)
from imdb_top250_scraper.models import Movie, OutputFormat
from imdb_top250_scraper.output import get_scraped_at, write_movies
from imdb_top250_scraper.parsing import extract_imdb_id, parse_rating
from imdb_top250_scraper.validation import validate_movies

LOGGER = logging.getLogger(__name__)


async def block_heavy_resources(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font"}:
        await route.abort()
    else:
        await route.continue_()


async def extract_movies(
    page: Page,
    include_images: bool = True,
    limit: int | None = None,
) -> list[Movie]:
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

    if limit is not None:
        raw_movies = raw_movies[:limit]

    results: list[Movie] = []
    for movie in raw_movies:
        rating, votes, votes_count = parse_rating(movie.pop("rating_text"))
        movie["imdb_id"] = extract_imdb_id(movie.get("imdb_url"))
        movie["rating"] = rating
        movie["votes"] = votes
        movie["votes_count"] = votes_count
        if not include_images:
            movie.pop("image_url", None)
        results.append(movie)

    validate_movies(results)
    return results


async def scrape_imdb_top_250(
    output_path: Path,
    output_format: OutputFormat = "json",
    include_images: bool = True,
    limit: int | None = None,
    pretty: bool = True,
    retries: int = DEFAULT_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
    locale: str = DEFAULT_LOCALE,
) -> list[Movie]:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            LOGGER.info("Scraping IMDb Top 250, attempt %s of %s", attempt, retries)
            return await scrape_once(
                output_path,
                output_format,
                include_images,
                limit,
                pretty,
                timeout_seconds,
                user_agent,
                locale,
            )
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break

            LOGGER.warning("Scrape attempt %s failed: %s", attempt, exc)
            await asyncio.sleep(attempt)

    raise RuntimeError(f"Failed to scrape IMDb Top 250 after {retries} attempts.") from last_error


async def scrape_once(
    output_path: Path,
    output_format: OutputFormat,
    include_images: bool,
    limit: int | None,
    pretty: bool,
    timeout_seconds: int,
    user_agent: str,
    locale: str,
) -> list[Movie]:
    browser: Browser | None = None
    timeout_ms = timeout_seconds * 1000

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale=locale,
                user_agent=user_agent,
                extra_http_headers={"Accept-Language": f"{locale},{locale.split('-')[0]};q=0.9"},
            )
            page = await context.new_page()
            await page.route("**/*", block_heavy_resources)

            await page.goto(IMDB_TOP_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_selector(MOVIE_SELECTOR, timeout=timeout_ms)
            movie_count_expression = (
                f"() => document.querySelectorAll('{MOVIE_SELECTOR}').length "
                f">= {EXPECTED_MOVIE_COUNT}"
            )
            await page.wait_for_function(movie_count_expression, timeout=timeout_ms)

            results = await extract_movies(page, include_images=include_images, limit=limit)
            expected_count = limit or EXPECTED_MOVIE_COUNT
            if len(results) < expected_count:
                raise RuntimeError(f"Expected {expected_count} movies, got {len(results)}.")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_movies(
                results,
                output_path,
                output_format,
                scraped_at=get_scraped_at(),
                source_url=IMDB_TOP_URL,
                pretty=pretty,
            )

            return results
        finally:
            if browser is not None:
                await browser.close()
