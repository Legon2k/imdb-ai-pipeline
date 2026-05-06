from imdb_top250_scraper.models import Movie

REQUIRED_MOVIE_FIELDS = {
    "rank",
    "imdb_id",
    "title",
    "rating",
    "votes",
    "votes_count",
    "imdb_url",
}


def validate_movies(movies: list[Movie]) -> None:
    for index, movie in enumerate(movies, start=1):
        missing_fields = REQUIRED_MOVIE_FIELDS - movie.keys()
        if missing_fields:
            fields = ", ".join(sorted(missing_fields))
            raise ValueError(f"Movie #{index} is missing required fields: {fields}")

        if movie["rank"] != index:
            raise ValueError(f"Movie #{index} has invalid rank: {movie['rank']}")

        if not movie["title"]:
            raise ValueError(f"Movie #{index} is missing title.")

        if not movie["imdb_id"]:
            raise ValueError(f"Movie #{index} is missing IMDb ID.")
