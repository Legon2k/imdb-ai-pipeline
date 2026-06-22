import argparse
import asyncio
import logging
import os

from opentelemetry import trace

from imdb_top250_scraper.constants import (
    DEFAULT_LOCALE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
)
from imdb_top250_scraper.logger import setup_scraper_logging
from imdb_top250_scraper.scraper import scrape_imdb_top_250
from imdb_top250_scraper.telemetry import (
    initialize_trace_from_env,
    setup_otel_scraper,
)

# Retrieve the application version from environment variables (Runtime ENV)
APP_VERSION = os.getenv("APP_VERSION", "0.0.0-dev")

LOGGER = logging.getLogger(__name__)
tracer = None  # Will be initialized in main()


def positive_int(value: str) -> int:
    """Validates that the CLI argument is a positive integer."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def parse_args() -> argparse.Namespace:
    """Parses command line arguments for the scraper."""
    parser = argparse.ArgumentParser(
        description=f"Scrape IMDb Top 250 movies and push to Redis. Version: {APP_VERSION}"
    )

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
    parser.add_argument(
        "--chart",
        choices=["top", "moviemeter", "toptv", "tvmeter"],
        default="top",
        help="Chart to parse. Default: top",
    )
    return parser.parse_args()


async def main() -> None:
    """Main async entry point."""
    global tracer

    args = parse_args()

    # 1. Initialize OpenTelemetry SDK FIRST (before any logging)
    tracer = setup_otel_scraper(service_name="imdb-scraper")

    # 2. Initialize structured JSON logging (will now inject trace context)
    setup_scraper_logging(service_name="imdb-scraper", level=args.log_level)

    # 3. Initialize trace context from environment (BEFORE first traced logs)
    traceparent = initialize_trace_from_env()

    # 4. Wrap entire operation in a root span so all logs are traced
    with tracer.start_as_current_span("scraper_main_execution") as root_span:
        root_span.set_attribute("version", APP_VERSION)
        root_span.set_attribute("chart", args.chart)
        root_span.set_attribute("limit", args.limit or -1)

        if traceparent:
            LOGGER.info("Initialized trace context from SCRAPER_TRACEPARENT")
            root_span.set_attribute("trace.inherited", True)
        else:
            LOGGER.info("Starting new trace for scraping operation")
            root_span.set_attribute("trace.inherited", False)

        LOGGER.info(f"Scraping IMDb starting. Version: {APP_VERSION}.")

        try:
            # Call the scraper without file output arguments
            movies = await scrape_imdb_top_250(
                chart=args.chart,
                include_images=not args.no_images,
                limit=args.limit,
                retries=args.retries,
                timeout_seconds=args.timeout,
                user_agent=args.user_agent,
                locale=args.locale,
            )

            LOGGER.info("Successfully published %s movies to Redis stream.", len(movies))
            root_span.set_attribute("result.movie_count", len(movies))
        finally:
            # 1. Force flush and shutdown OpenTelemetry tracer provider before exit
            provider = trace.get_tracer_provider()
            if hasattr(provider, "shutdown"):
                LOGGER.info("Flushing OpenTelemetry buffers...")
                provider.shutdown()  # This blocks exit until all traces are sent

            # 2. Async hold container alive so Alloy can pull the remaining logs from the socket
            LOGGER.info("Waiting for log collector sync...")
            await asyncio.sleep(60)  # Safe async delay, no 'time' module dependency conflict


def run() -> None:
    """Synchronous wrapper for the async main function."""
    asyncio.run(main())
