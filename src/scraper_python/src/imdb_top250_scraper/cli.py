# --- START OF FILE cli.py ---

import argparse
import asyncio
import logging

from imdb_top250_scraper.constants import (
    DEFAULT_LOCALE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
)
from imdb_top250_scraper.scraper import scrape_imdb_top_250

LOGGER = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    """Validates that the CLI argument is a positive integer."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def parse_args() -> argparse.Namespace:
    """Parses command line arguments for the scraper."""
    parser = argparse.ArgumentParser(description="Scrape IMDb Top 250 movies and push to Redis.")

    # File output arguments (--output, --format, --pretty) were removed
    # since we now use a message broker (Redis) for data ingestion.

    parser.add_argument(
        "--limit",
        type=positive_int,
        default=None,
        help="Limit the number of movies scraped.",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Page operation timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="Browser user agent.",
    )
    parser.add_argument(
        "--locale",
        default=DEFAULT_LOCALE,
        help=f"Browser locale and Accept-Language preference. Default: {DEFAULT_LOCALE}",
    )
    parser.add_argument(
        "--retries",
        type=positive_int,
        default=DEFAULT_RETRIES,
        help=f"Number of scrape attempts. Default: {DEFAULT_RETRIES}",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity. Default: INFO",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Omit image_url from output records.",
    )
    return parser.parse_args()


async def main() -> None:
    """Main async entry point."""
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(message)s")

    # Call the scraper without file output arguments
    movies = await scrape_imdb_top_250(
        include_images=not args.no_images,
        limit=args.limit,
        retries=args.retries,
        timeout_seconds=args.timeout,
        user_agent=args.user_agent,
        locale=args.locale,
    )

    LOGGER.info("Successfully pushed %s movies to Redis queue.", len(movies))


def run() -> None:
    """Synchronous wrapper for the async main function."""
    asyncio.run(main())
