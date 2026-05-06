from pathlib import Path

IMDB_TOP_URL = "https://www.imdb.com/chart/top/"
MOVIE_SELECTOR = ".ipc-metadata-list-summary-item"
EXPECTED_MOVIE_COUNT = 250
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_OUTPUT_STEM = "imdb_top_250"
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_LOCALE = "en-US"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
