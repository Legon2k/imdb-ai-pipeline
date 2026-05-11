import json
import os
import sys
import unittest
from pathlib import Path

# Attempt to import the package; if it's not importable (tests run via discovery),
# add the src/ directory to sys.path and try again.
try:
    from imdb_top250_scraper.output import format_movies, get_default_output_path
    from imdb_top250_scraper.parsing import extract_imdb_id, parse_rating, parse_votes_count
    from imdb_top250_scraper.validation import validate_movies
except Exception:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from imdb_top250_scraper.output import format_movies, get_default_output_path
    from imdb_top250_scraper.parsing import extract_imdb_id, parse_rating, parse_votes_count
    from imdb_top250_scraper.validation import validate_movies

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ParseRatingTest(unittest.TestCase):
    def test_parse_rating_with_votes_suffix(self):
        self.assertEqual(parse_rating("9.3\n (3.2M)"), (9.3, "3.2M", 3_200_000))

    def test_parse_rating_without_votes(self):
        self.assertEqual(parse_rating("8.2"), (8.2, None, None))

    def test_parse_rating_empty_value(self):
        self.assertEqual(parse_rating(""), (None, None, None))

    def test_parse_votes_count_with_suffixes(self):
        self.assertEqual(parse_votes_count("116K"), 116_000)
        self.assertEqual(parse_votes_count("2.2M"), 2_200_000)
        self.assertEqual(parse_votes_count("1B"), 1_000_000_000)

    def test_parse_votes_count_with_plain_number(self):
        self.assertEqual(parse_votes_count("123,456"), 123_456)

    def test_parse_votes_count_unknown_format(self):
        self.assertIsNone(parse_votes_count("not available"))


class OutputFormatTest(unittest.TestCase):
    def test_default_output_path_uses_format_extension(self):
        self.assertEqual(get_default_output_path("json").name, "imdb_top_250.json")
        self.assertEqual(get_default_output_path("jsonl").name, "imdb_top_250.jsonl")

    def test_format_movies_as_json(self):
        content = format_movies(
            [
                {
                    "rank": 1,
                    "imdb_id": "tt0111161",
                    "title": "Movie",
                    "rating": 9.3,
                    "votes": "3.2M",
                    "votes_count": 3_200_000,
                    "imdb_url": "https://www.imdb.com/title/tt0111161/",
                }
            ],
            "json",
            scraped_at="2026-05-06T12:00:00Z",
            source_url="https://example.com/chart",
            pretty=True,
        )

        self.assertIn('"scraped_at": "2026-05-06T12:00:00Z"', content)
        self.assertIn('"source_url": "https://example.com/chart"', content)
        self.assertIn('"movies": [', content)
        self.assertIn('"rank": 1', content)
        self.assertTrue(content.startswith("{"))

    def test_format_movies_as_jsonl(self):
        content = format_movies(
            [
                {
                    "rank": 1,
                    "imdb_id": "tt0111161",
                    "title": "First",
                    "rating": 9.3,
                    "votes": "3.2M",
                    "votes_count": 3_200_000,
                    "imdb_url": "https://www.imdb.com/title/tt0111161/",
                },
                {
                    "rank": 2,
                    "imdb_id": "tt0068646",
                    "title": "Second",
                    "rating": 9.2,
                    "votes": "2.2M",
                    "votes_count": 2_200_000,
                    "imdb_url": "https://www.imdb.com/title/tt0068646/",
                },
            ],
            "jsonl",
            scraped_at="2026-05-06T12:00:00Z",
            source_url="https://example.com/chart",
            pretty=True,
        )

        rows = [json.loads(line) for line in content.splitlines()]

        self.assertEqual(rows[0]["scraped_at"], "2026-05-06T12:00:00Z")
        self.assertEqual(rows[0]["source_url"], "https://example.com/chart")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[1]["rank"], 2)

    def test_format_movies_as_compact_json(self):
        content = format_movies(
            [
                {
                    "rank": 1,
                    "imdb_id": "tt0111161",
                    "title": "Movie",
                    "rating": 9.3,
                    "votes": "3.2M",
                    "votes_count": 3_200_000,
                    "imdb_url": "https://www.imdb.com/title/tt0111161/",
                }
            ],
            "json",
            scraped_at="2026-05-06T12:00:00Z",
            source_url="https://example.com/chart",
            pretty=False,
        )

        self.assertNotIn("\n", content)
        self.assertIn('"movies":[', content)


class MovieValidationTest(unittest.TestCase):
    def test_validate_movies_accepts_required_fields_without_image_url(self):
        validate_movies(
            [
                {
                    "rank": 1,
                    "imdb_id": "tt0111161",
                    "title": "The Shawshank Redemption",
                    "rating": 9.3,
                    "votes": "3.2M",
                    "votes_count": 3_200_000,
                    "imdb_url": "https://www.imdb.com/title/tt0111161/",
                }
            ]
        )

    def test_validate_movies_rejects_missing_required_field(self):
        with self.assertRaisesRegex(ValueError, "imdb_id"):
            validate_movies(
                [
                    {
                        "rank": 1,
                        "title": "The Shawshank Redemption",
                        "rating": 9.3,
                        "votes": "3.2M",
                        "votes_count": 3_200_000,
                        "imdb_url": "https://www.imdb.com/title/tt0111161/",
                    }
                ]
            )

    def test_validate_movies_rejects_invalid_rank(self):
        with self.assertRaisesRegex(ValueError, "invalid rank"):
            validate_movies(
                [
                    {
                        "rank": 2,
                        "imdb_id": "tt0111161",
                        "title": "The Shawshank Redemption",
                        "rating": 9.3,
                        "votes": "3.2M",
                        "votes_count": 3_200_000,
                        "imdb_url": "https://www.imdb.com/title/tt0111161/",
                    }
                ]
            )


class ImdbIdTest(unittest.TestCase):
    def test_extract_imdb_id_from_title_url(self):
        self.assertEqual(
            extract_imdb_id("https://www.imdb.com/title/tt0111161/?ref_=chttp_t_1"),
            "tt0111161",
        )

    def test_extract_imdb_id_from_path(self):
        self.assertEqual(extract_imdb_id("/title/tt0068646/"), "tt0068646")

    def test_extract_imdb_id_missing_value(self):
        self.assertIsNone(extract_imdb_id(None))
        self.assertIsNone(extract_imdb_id("https://www.imdb.com/chart/top/"))


class SchemaTest(unittest.TestCase):
    def test_json_schema_files_are_valid_json(self):
        schema_paths = [
            PROJECT_ROOT / "schema" / "imdb_top_250.schema.json",
            PROJECT_ROOT / "schema" / "imdb_top_250_jsonl_line.schema.json",
        ]

        for schema_path in schema_paths:
            with self.subTest(schema_path=schema_path):
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertIn("required", schema)


if __name__ == "__main__":
    unittest.main()
