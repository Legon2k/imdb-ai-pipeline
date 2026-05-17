"""
Shared data contracts for IMDB AI Pipeline.

This package contains the single source of truth for all data structures
used across the microservices architecture.

Available contracts:
- MoviePayload: Core movie data (Scraper → Redis → Database)
- AITaskPayload: AI enrichment tasks (API → Redis → AI Worker)
- DatabaseMovie: Complete database record with metadata

Usage:
    from contracts.python_contracts import MoviePayload, AITaskPayload

    # Validate incoming data
    movie = MoviePayload.model_validate_json(json_payload)

    # Create AI task
    task = AITaskPayload(id=movie_id, rank=1, title="...", rating=9.3)
"""

from .python_contracts import (
    MoviePayload,
    AITaskPayload,
    DatabaseMovie,
    MoviePayloadDict,
    AITaskPayloadDict,
)

__all__ = [
    "MoviePayload",
    "AITaskPayload",
    "DatabaseMovie",
    "MoviePayloadDict",
    "AITaskPayloadDict",
]
