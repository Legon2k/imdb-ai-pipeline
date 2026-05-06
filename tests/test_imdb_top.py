import unittest

from imdb_top import parse_rating, parse_votes_count


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


if __name__ == "__main__":
    unittest.main()
