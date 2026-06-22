import asyncio
import logging

from opentelemetry import trace
from playwright.async_api import Browser, Page, Route, async_playwright
from playwright.async_api import Error as PlaywrightError

from imdb_top250_scraper.constants import (
    DEFAULT_LOCALE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    IMDB_CHARTS,
    MOVIE_SELECTOR,
    ChartInfo,
)
from imdb_top250_scraper.models import Movie
from imdb_top250_scraper.parsing import extract_imdb_id, parse_rating
from imdb_top250_scraper.telemetry import (
    get_traceparent,
)
from imdb_top250_scraper.validation import validate_movies

# Import our new Redis publisher
from .redis_publisher import RedisPublisher

LOGGER = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


async def block_heavy_resources(route: Route) -> None:
    """Blocks images, media, and fonts to speed up page loading."""
    try:
        if route.request.resource_type in {"image", "media", "font"}:
            await route.abort()
        else:
            await route.continue_()
    except PlaywrightError:
        # Ignore errors if the browser closes while network requests are still pending
        pass


async def extract_movies(
    page: Page,
    include_images: bool = True,
    limit: int | None = None,
) -> list[Movie]:
    """
    Extracts raw movie data from the DOM and formats it according
    to the shared MoviePayload contract.
    """
    with tracer.start_as_current_span("extract_movies") as span:
        span.set_attribute("include_images", include_images)
        span.set_attribute("limit", limit or -1)

        movies = page.locator(MOVIE_SELECTOR)

        raw_movies = await movies.evaluate_all(
            """
            items => items.map((item, index) => {
                const titleText = item.querySelector(".ipc-title__text")?.textContent?.trim() || "";
                
                // Try multiple selectors for rating to improve robustness
                let ratingText = "";
                const ratingSpan = 
                    item.querySelector("span[aria-label*='IMDb rating']") ||
                    item.querySelector("span[aria-label*='rating']") ||
                    item.querySelector(".ratingGroup--imdb-rating span");
                
                if (ratingSpan) {
                    ratingText = ratingSpan.textContent?.trim() || "";
                }
                
                // If still empty, try to find any span with numeric rating pattern
                if (!ratingText) {
                    const spans = item.querySelectorAll("span");
                    for (const span of spans) {
                        const text = span.textContent?.trim() || "";
                        if (/^\\d+(?:\\.\\d+)?\\s*\\(/.test(text)) {
                            ratingText = text;
                            break;
                        }
                    }
                }
                
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
            imdb_id = extract_imdb_id(movie.get("imdb_url"))

            # Log warning if rating is 0 (new movie without rating)
            if rating == 0.0:
                LOGGER.warning(
                    "Movie #%d (%s) has no rating (new movie). rating_text='%s', url='%s'",
                    movie["rank"],
                    movie["title"],
                    movie.get("rating_text", ""),
                    movie.get("imdb_url", ""),
                )

            # Map to shared MoviePayload contract - only keep required fields
            movie_payload: Movie = {
                "imdb_id": imdb_id,
                "rank": movie["rank"],
                "title": movie["title"],
                "rating": rating,
                "votes": votes,
            }

            # Add optional image_url if requested and available
            if include_images and movie.get("image_url"):
                movie_payload["image_url"] = movie["image_url"]

            results.append(movie_payload)

        validate_movies(results)
        span.set_attribute("extracted_count", len(results))
        return results


async def scrape_imdb_top_250(
    chart: str = "top",
    include_images: bool = True,
    limit: int | None = None,
    retries: int = DEFAULT_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
    locale: str = DEFAULT_LOCALE,
) -> list[Movie]:
    """Entry point with retry logic for scraping IMDb."""
    with tracer.start_as_current_span("scrape_imdb_top_250") as span:
        span.set_attribute("chart", chart)
        span.set_attribute("include_images", include_images)
        span.set_attribute("limit", limit or -1)
        span.set_attribute("retries", retries)
        span.set_attribute("timeout_seconds", timeout_seconds)

        last_error: Exception | None = None

        search_term = f"/{chart}/"  # Will be used to identify the chart to scrape

        chartInfo = next((i for i in IMDB_CHARTS if search_term in i.url), IMDB_CHARTS[0])

        for attempt in range(1, retries + 1):
            try:
                LOGGER.info(
                    "Scraping %s, count: %s, attempt %s of %s",
                    chartInfo.description,
                    chartInfo.limit,
                    attempt,
                    retries,
                )
                return await scrape_once(
                    chartInfo,
                    include_images,
                    limit,
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
    chartInfo: ChartInfo,
    include_images: bool,
    limit: int | None,
    timeout_seconds: int,
    user_agent: str,
    locale: str,
) -> list[Movie]:
    """Single execution of the scraping logic using Playwright."""
    with tracer.start_as_current_span("scrape_once") as span:
        span.set_attribute("chart.url", chartInfo.url)
        span.set_attribute("chart.description", chartInfo.description)
        span.set_attribute("chart.limit", chartInfo.limit)

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

                await page.goto(chartInfo.url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_selector(MOVIE_SELECTOR, timeout=timeout_ms)
                movie_count_expression = (
                    f"() => document.querySelectorAll('{MOVIE_SELECTOR}').length >= {chartInfo.limit}"
                )
                await page.wait_for_function(movie_count_expression, timeout=timeout_ms)

                results = await extract_movies(page, include_images=include_images, limit=limit)
                expected_count = limit or chartInfo.limit
                if len(results) < expected_count:
                    raise RuntimeError(f"Expected {expected_count} movies, got {len(results)}.")

                # ==========================================
                # ENTERPRISE DATA PIPELINE: Push to Redis
                # ==========================================
                LOGGER.info("Successfully extracted %d movies. Pushing to Redis...", len(results))

                with tracer.start_as_current_span("publish_to_redis") as publish_span:
                    publish_span.set_attribute("movie_count", len(results))

                    publisher = RedisPublisher()
                    published_count = 0

                    for movie in results:
                        with tracer.start_as_current_span("publish_movie_to_redis") as child_span:
                            child_span.set_attribute("movie.imdb_id", movie["imdb_id"])
                            child_span.set_attribute("movie.title", movie["title"])

                            # Ensure the movie object is a dictionary before pushing
                            movie_dict = dict(movie) if not isinstance(movie, dict) else movie

                            movie_dict["traceparent"] = get_traceparent()  # Add trace context for distributed tracing

                            success = publisher.publish_movie(movie_dict)
                            if success:
                                published_count += 1

                    LOGGER.info(
                        "Successfully published %d/%d movies to Redis.",
                        published_count,
                        len(results),
                    )
                    publish_span.set_attribute("published_count", published_count)
                # ==========================================

                span.set_attribute("result_count", len(results))
                return results
            finally:
                if browser is not None:
                    await browser.close()
