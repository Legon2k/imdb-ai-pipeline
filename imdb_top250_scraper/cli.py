import argparse
import asyncio
import logging
from pathlib import Path

from imdb_top250_scraper.constants import (
    DEFAULT_LOCALE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
)
from imdb_top250_scraper.output import get_default_output_path
from imdb_top250_scraper.scraper import scrape_imdb_top_250

LOGGER = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


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
        "--limit",
        type=positive_int,
        default=None,
        help="Limit the number of movies written to the output file.",
    )
    output_style = parser.add_mutually_exclusive_group()
    output_style.add_argument(
        "--pretty",
        dest="pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output. Default for JSON.",
    )
    output_style.add_argument(
        "--compact",
        dest="pretty",
        action="store_false",
        help="Write compact JSON output. JSONL is always one compact object per line.",
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
    args = parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(message)s")
    output_path = args.output or get_default_output_path(args.format)
    movies = await scrape_imdb_top_250(
        output_path,
        output_format=args.format,
        include_images=not args.no_images,
        limit=args.limit,
        pretty=args.pretty,
        retries=args.retries,
        timeout_seconds=args.timeout,
        user_agent=args.user_agent,
        locale=args.locale,
    )
    LOGGER.info("Saved %s movies to %s", len(movies), output_path)


def run() -> None:
    asyncio.run(main())
