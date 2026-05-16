import os
import sys
import unittest

# Attempt to import the package; if it's not importable (tests run via discovery),
# add the src/ directory to sys.path and try again.
try:
    from imdb_top250_scraper.parsing import extract_imdb_id, parse_rating, parse_votes_count
    from imdb_top250_scraper.validation import validate_movies
except Exception:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from imdb_top250_scraper.parsing import extract_imdb_id, parse_rating, parse_votes_count
    from imdb_top250_scraper.validation import validate_movies


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


if __name__ == "__main__":
    unittest.main()
