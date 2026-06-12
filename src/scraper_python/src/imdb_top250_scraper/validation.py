"""
Validation for scraped movie data.

Validates that movies conform to the shared MoviePayload contract.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))
from contracts import MoviePayload

sys.path.insert(0, os.path.dirname(__file__))
from imdb_top250_scraper.models import Movie


def validate_movies(movies: list[Movie]) -> None:
    """
    Validates that each movie conforms to the shared MoviePayload contract.

    Uses Pydantic validation from the shared contract to ensure consistency
    across the entire pipeline.
    """
    for index, movie in enumerate(movies, start=1):
        try:
            # Validate against the shared contract
            MoviePayload(**movie)
        except Exception as e:
            # Provide more detailed error message with movie info
            movie_title = movie.get("title", "Unknown")
            movie_url = movie.get("imdb_url", "N/A")
            raise ValueError(
                f"Movie #{index} ({movie_title}) failed validation: {e}\n"
                f"URL: {movie_url}\nMovie data: {movie}"
            ) from e

        # Additional rank validation
        if movie.get("rank") != index:
            raise ValueError(f"Movie #{index} has invalid rank: {movie.get('rank')}")
