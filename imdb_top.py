import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import Browser, Route, async_playwright


IMDB_TOP_URL = "https://www.imdb.com/chart/top/"
MOVIE_SELECTOR = ".ipc-metadata-list-summary-item"
EXPECTED_MOVIE_COUNT = 250
DEFAULT_OUTPUT_PATH = Path(__file__).with_name("imdb_top_250.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def block_heavy_resources(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font"}:
        await route.abort()
    else:
        await route.continue_()


def parse_rating(raw_rating: str) -> tuple[float | None, str | None]:
    cleaned = " ".join(raw_rating.split()).replace("\xa0", " ")
    match = re.search(r"(?P<rating>\d+(?:\.\d+)?)\s*(?:\((?P<votes>[^)]+)\))?", cleaned)

    if not match:
        return None, None

    return float(match.group("rating")), match.group("votes")


async def extract_movies(page) -> list[dict]:
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
        rating, votes = parse_rating(movie.pop("rating_text"))
        movie["rating"] = rating
        movie["votes"] = votes
        results.append(movie)

    return results


async def scrape_imdb_top_250(output_path: Path = DEFAULT_OUTPUT_PATH) -> list[dict]:
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
            await page.wait_for_function(
                f"() => document.querySelectorAll('{MOVIE_SELECTOR}').length >= {EXPECTED_MOVIE_COUNT}",
                timeout=30_000,
            )

            results = await extract_movies(page)
            if len(results) < EXPECTED_MOVIE_COUNT:
                raise RuntimeError(
                    f"Expected {EXPECTED_MOVIE_COUNT} movies, got {len(results)}."
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            return results
        finally:
            if browser is not None:
                await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape IMDb Top 250 movies to JSON.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path. Default: {DEFAULT_OUTPUT_PATH}",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    movies = await scrape_imdb_top_250(args.output)
    print(f"Saved {len(movies)} movies to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
