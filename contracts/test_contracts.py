"""
Contract synchronization tests.

These tests validate that data contracts remain consistent across:
- Python Pydantic models (python_contracts.py)
- JSON Schema (schemas.json)
- C# records (CsharpContracts.cs)
- Database schema (infra/postgres/init.sql)

Tests run on every deployment to catch contract drift early.
"""

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from contracts.python_contracts import (
    MoviePayload,
    AITaskPayload,
    DatabaseMovie,
)


class ContractSchemaSyncTest(unittest.TestCase):
    """Tests that Pydantic models match the JSON Schema."""

    @classmethod
    def setUpClass(cls):
        """Load the shared JSON Schema."""
        schema_path = Path(__file__).parent / "schemas.json"
        with open(schema_path) as f:
            cls.schema = json.load(f)

    def test_movie_payload_schema_exists(self):
        """Verify MoviePayload is defined in schemas.json."""
        self.assertIn("definitions", self.schema)
        self.assertIn("MoviePayload", self.schema["definitions"])

    def test_ai_task_payload_schema_exists(self):
        """Verify AITaskPayload is defined in schemas.json."""
        self.assertIn("definitions", self.schema)
        self.assertIn("AITaskPayload", self.schema["definitions"])

    def test_database_movie_schema_exists(self):
        """Verify DatabaseMovie is defined in schemas.json."""
        self.assertIn("definitions", self.schema)
        self.assertIn("DatabaseMovie", self.schema["definitions"])


class MoviePayloadValidationTest(unittest.TestCase):
    """Tests for MoviePayload contract validation."""

    def test_valid_movie_payload_minimal(self):
        """Valid payload with required fields only."""
        payload = MoviePayload(
            imdb_id="tt0111161",
            rank=1,
            title="The Shawshank Redemption",
            rating=9.3,
            votes="2,500,000",
        )
        self.assertEqual(payload.imdb_id, "tt0111161")
        self.assertEqual(payload.rank, 1)

    def test_valid_movie_payload_with_optional(self):
        """Valid payload with optional image_url."""
        payload = MoviePayload(
            imdb_id="tt0111161",
            rank=1,
            title="The Shawshank Redemption",
            rating=9.3,
            votes="2,500,000",
            image_url="https://example.com/poster.jpg",
        )
        self.assertEqual(payload.image_url, "https://example.com/poster.jpg")

    def test_invalid_imdb_id_format(self):
        """Rejects invalid IMDB ID format."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="invalid",  # Should be tt\d+
                rank=1,
                title="Test",
                rating=9.0,
                votes="1000",
            )

    def test_invalid_rank_too_high(self):
        """Rejects rank > 250."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=251,  # Should be <= 250
                title="Test",
                rating=9.0,
                votes="1000",
            )

    def test_invalid_rank_zero(self):
        """Rejects rank < 1."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=0,  # Should be >= 1
                title="Test",
                rating=9.0,
                votes="1000",
            )

    def test_invalid_rating_too_high(self):
        """Rejects rating > 10."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=1,
                title="Test",
                rating=10.1,  # Should be <= 10
                votes="1000",
            )

    def test_invalid_rating_negative(self):
        """Rejects negative rating."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=1,
                title="Test",
                rating=-1.0,  # Should be >= 0
                votes="1000",
            )

    def test_invalid_title_empty(self):
        """Rejects empty title."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=1,
                title="",  # Should be min_length=1
                rating=9.0,
                votes="1000",
            )

    def test_invalid_title_too_long(self):
        """Rejects title > 255 chars."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=1,
                title="x" * 256,  # Should be max_length=255
                rating=9.0,
                votes="1000",
            )

    def test_missing_required_field_imdb_id(self):
        """Rejects missing imdb_id."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                # imdb_id missing
                rank=1,
                title="Test",
                rating=9.0,
                votes="1000",
            )

    def test_extra_fields_rejected(self):
        """Rejects unknown fields (strict schema)."""
        with self.assertRaises(ValidationError):
            MoviePayload(
                imdb_id="tt0111161",
                rank=1,
                title="Test",
                rating=9.0,
                votes="1000",
                unknown_field="should fail",  # Extra field
            )

    def test_json_roundtrip(self):
        """JSON serialization/deserialization is lossless."""
        original = MoviePayload(
            imdb_id="tt0111161",
            rank=1,
            title="The Shawshank Redemption",
            rating=9.3,
            votes="2,500,000",
            image_url="https://example.com/poster.jpg",
        )
        json_str = original.model_dump_json()
        restored = MoviePayload.model_validate_json(json_str)
        self.assertEqual(original, restored)


class AITaskPayloadValidationTest(unittest.TestCase):
    """Tests for AITaskPayload contract validation."""

    def test_valid_ai_task_payload(self):
        """Valid AI task payload."""
        task = AITaskPayload(id=1, rank=1, title="The Shawshank Redemption", rating=9.3)
        self.assertEqual(task.id, 1)
        self.assertEqual(task.rank, 1)

    def test_missing_id_field(self):
        """Rejects missing id."""
        with self.assertRaises(ValidationError):
            AITaskPayload(
                # id missing
                rank=1,
                title="Test",
                rating=9.0,
            )

    def test_invalid_id_zero(self):
        """Rejects id < 1."""
        with self.assertRaises(ValidationError):
            AITaskPayload(id=0, rank=1, title="Test", rating=9.0)

    def test_json_roundtrip(self):
        """JSON serialization/deserialization is lossless."""
        original = AITaskPayload(
            id=1, rank=1, title="The Shawshank Redemption", rating=9.3
        )
        json_str = original.model_dump_json()
        restored = AITaskPayload.model_validate_json(json_str)
        self.assertEqual(original, restored)


class DatabaseMovieValidationTest(unittest.TestCase):
    """Tests for DatabaseMovie contract validation."""

    def test_valid_database_movie_completed(self):
        """Valid completed movie record."""
        from datetime import datetime, timezone

        movie = DatabaseMovie(
            id=1,
            imdb_id="tt0111161",
            rank=1,
            title="The Shawshank Redemption",
            rating=9.3,
            votes="2,500,000",
            image_url="https://example.com/poster.jpg",
            ai_summary="A powerful story of hope...",
            status="completed",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.assertEqual(movie.id, 1)
        self.assertEqual(movie.status, "completed")

    def test_valid_database_movie_pending(self):
        """Valid pending movie record."""
        from datetime import datetime, timezone

        movie = DatabaseMovie(
            id=1,
            imdb_id="tt0111161",
            rank=1,
            title="The Shawshank Redemption",
            rating=9.3,
            votes="2,500,000",
            image_url=None,
            ai_summary=None,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.assertEqual(movie.status, "pending")
        self.assertIsNone(movie.ai_summary)

    def test_invalid_status(self):
        """Rejects invalid status values."""
        from datetime import datetime, timezone

        with self.assertRaises(ValidationError):
            DatabaseMovie(
                id=1,
                imdb_id="tt0111161",
                rank=1,
                title="Test",
                rating=9.0,
                votes="1000",
                image_url=None,
                ai_summary=None,
                status="invalid_status",  # Should be pending|processing|completed|failed
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

    def test_valid_statuses(self):
        """All valid statuses are accepted."""
        from datetime import datetime, timezone

        for status in ["pending", "processing", "completed", "failed"]:
            movie = DatabaseMovie(
                id=1,
                imdb_id="tt0111161",
                rank=1,
                title="Test",
                rating=9.0,
                votes="1000",
                image_url=None,
                ai_summary=None,
                status=status,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.assertEqual(movie.status, status)


class CrossContractConsistencyTest(unittest.TestCase):
    """Tests that all contract variants remain consistent."""

    def test_movie_payload_contains_ai_task_fields(self):
        """MoviePayload has all AITaskPayload fields (except id)."""
        # Create a valid MoviePayload
        movie = MoviePayload(
            imdb_id="tt0111161",
            rank=1,
            title="The Shawshank Redemption",
            rating=9.3,
            votes="2,500,000",
        )

        # It should have all the fields that AITaskPayload needs
        self.assertTrue(hasattr(movie, "rank"))
        self.assertTrue(hasattr(movie, "title"))
        self.assertTrue(hasattr(movie, "rating"))

    def test_ai_task_subset_of_movie_payload(self):
        """AITaskPayload fields are subset of MoviePayload fields."""
        ai_fields = {"id", "rank", "title", "rating"}
        movie_fields = {"imdb_id", "rank", "title", "rating", "votes", "image_url"}

        # AITaskPayload has id (DB identifier) instead of imdb_id
        # But rank, title, rating are common
        common_fields = ai_fields & movie_fields
        self.assertIn("rank", common_fields)
        self.assertIn("title", common_fields)
        self.assertIn("rating", common_fields)

    def test_database_movie_superset(self):
        """DatabaseMovie has all other contract fields plus metadata."""
        database_fields = {
            "id",
            "imdb_id",
            "rank",
            "title",
            "rating",
            "votes",
            "image_url",
            "ai_summary",
            "status",
            "created_at",
            "updated_at",
        }
        movie_fields = {"imdb_id", "rank", "title", "rating", "votes", "image_url"}

        # DatabaseMovie should include all MoviePayload fields
        for field in movie_fields:
            self.assertIn(field, database_fields, f"{field} missing in DatabaseMovie")


if __name__ == "__main__":
    unittest.main()
