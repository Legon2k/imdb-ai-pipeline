"""
Data models for the IMDb scraper.

Uses shared contracts from the contracts package to ensure consistency
across the entire pipeline.
"""

import os
import sys
from typing import NotRequired, TypedDict

# Import shared contract
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))
from contracts import MoviePayload as SharedMoviePayload

# Re-export the shared contract for convenience
MoviePayload = SharedMoviePayload


# Internal intermediate representation during scraping
# (before conversion to shared MoviePayload)
class RawMovie(TypedDict):
    """Intermediate movie data extracted from DOM before validation and mapping."""

    rank: int
    imdb_id: str | None
    title: str
    rating: float | None
    votes: str | None
    votes_count: int | None
    imdb_url: str | None
    image_url: NotRequired[str | None]


# Backward compatibility alias (for existing code that imports Movie)
Movie = SharedMoviePayload
