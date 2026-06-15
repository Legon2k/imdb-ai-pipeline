import json
import logging
import sys
from datetime import UTC, datetime


class ScraperJsonFormatter(logging.Formatter):
    """
    Standard JSON formatter for cloud-native logging.
    Outputs logs in structured JSON format with essential metadata.
    """

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        log_record = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service_name": self.service_name,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_scraper_logging(service_name: str = "imdb-scraper", level: str | int = logging.INFO):
    """
    Configures the root logger to redirect all output to stdout in JSON format
    with a dynamically specified log level.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ScraperJsonFormatter(service_name))

    root_logger = logging.getLogger()
    # Remove existing raw-text handlers
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
