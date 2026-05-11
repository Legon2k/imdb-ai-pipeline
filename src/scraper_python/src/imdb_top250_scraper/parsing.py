import re


def parse_rating(raw_rating: str) -> tuple[float | None, str | None, int | None]:
    cleaned = " ".join(raw_rating.split()).replace("\xa0", " ")
    match = re.search(r"(?P<rating>\d+(?:\.\d+)?)\s*(?:\((?P<votes>[^)]+)\))?", cleaned)

    if not match:
        return None, None, None

    votes = match.group("votes")
    return float(match.group("rating")), votes, parse_votes_count(votes)


def parse_votes_count(raw_votes: str | None) -> int | None:
    if not raw_votes:
        return None

    cleaned = raw_votes.strip().replace(",", "").upper()
    match = re.fullmatch(r"(?P<number>\d+(?:\.\d+)?)(?P<suffix>[KMB])?", cleaned)
    if not match:
        return None

    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    multiplier = multipliers.get(match.group("suffix"), 1)
    return int(float(match.group("number")) * multiplier)


def extract_imdb_id(imdb_url: str | None) -> str | None:
    if not imdb_url:
        return None

    match = re.search(r"/title/(?P<imdb_id>tt\d+)/?", imdb_url)
    if not match:
        return None

    return match.group("imdb_id")
