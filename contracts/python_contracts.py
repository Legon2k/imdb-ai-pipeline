"""
Shared data contracts for the IMDB AI Pipeline.

This module defines Pydantic models that serve as the single source of truth
for all data structures across the pipeline. These contracts are used for:
- Validation at each service boundary
- Type hints across services
- OpenAPI/JSON Schema generation
- Contract testing to prevent field drift

All models are derived from contracts/schemas.json
"""

from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class MoviePayload(BaseModel):
    """
    Core movie data structure flowing through: Scraper → Redis → .NET Worker → Database.

    This is the canonical contract for scraped movie data.
    Used by:
    - Scraper: publishes to 'movies_stream'
    - .NET Worker: deserializes from Redis stream
    - Database: persisted in movies table
    """

    imdb_id: str = Field(
        ..., pattern=r"^tt\d+$", description="IMDB identifier (e.g., 'tt0111161')"
    )
    rank: int = Field(..., ge=1, le=250, description="IMDB Top 250 ranking position")
    title: str = Field(..., min_length=1, max_length=255, description="Movie title")
    rating: float = Field(..., ge=0, le=10, description="IMDB rating (0.0-10.0)")
    votes: str = Field(
        ..., description="Number of votes (formatted string, e.g., '1,234,567')"
    )
    image_url: Optional[str] = Field(None, description="URL to movie poster image")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "imdb_id": "tt0111161",
                "rank": 1,
                "title": "The Shawshank Redemption",
                "rating": 9.3,
                "votes": "2,500,000",
                "image_url": "https://example.com/poster.jpg",
            }
        }
    )


class AITaskPayload(BaseModel):
    """
    Subset of movie data used for AI enrichment tasks.

    This is a specialized contract flowing: API → Redis 'ai_stream' → AI Worker.
    Contains only the fields needed for LLM processing.

    Used by:
    - FastAPI: creates from database records
    - AI Worker: validates and processes
    """

    id: int = Field(..., ge=1, description="Database movie ID (internal surrogate key)")
    rank: int = Field(..., ge=1, le=250, description="IMDB Top 250 ranking position")
    title: str = Field(..., min_length=1, max_length=255, description="Movie title")
    rating: float = Field(..., ge=0, le=10, description="IMDB rating (0.0-10.0)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "rank": 1,
                "title": "The Shawshank Redemption",
                "rating": 9.3,
            }
        }
    )


class DatabaseMovie(BaseModel):
    """
    Complete movie record as persisted in PostgreSQL.

    This is the response contract for API endpoints.
    Used by:
    - FastAPI: response_model for GET /movies
    - Tests: database validation
    """

    id: int = Field(..., description="Primary key")
    imdb_id: str = Field(..., description="IMDB identifier")
    rank: int = Field(..., ge=1, le=250, description="IMDB Top 250 ranking")
    title: str = Field(..., max_length=255, description="Movie title")
    rating: float = Field(..., ge=0, le=10, description="IMDB rating")
    votes: str = Field(..., description="Number of votes")
    image_url: Optional[str] = Field(None, description="Poster image URL")
    ai_summary: Optional[str] = Field(None, description="AI-generated summary")
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        ..., description="Processing status"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "imdb_id": "tt0111161",
                "rank": 1,
                "title": "The Shawshank Redemption",
                "rating": 9.3,
                "votes": "2,500,000",
                "image_url": "https://example.com/poster.jpg",
                "ai_summary": "A powerful story of hope and friendship...",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            }
        }
    )


# For backward compatibility, also define as TypedDict
# (useful when you need dict interface, not validation)
try:
    from typing import TypedDict, NotRequired

    class MoviePayloadDict(TypedDict, total=False):
        """TypedDict version of MoviePayload for use in type hints."""

        imdb_id: str
        rank: int
        title: str
        rating: float
        votes: str
        image_url: NotRequired[str | None]

    class AITaskPayloadDict(TypedDict):
        """TypedDict version of AITaskPayload for use in type hints."""

        id: int
        rank: int
        title: str
        rating: float

except ImportError:
    # Python < 3.10 compatibility
    MoviePayloadDict = None
    AITaskPayloadDict = None
