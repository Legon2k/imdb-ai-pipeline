from typing import Literal, NotRequired, TypedDict

OutputFormat = Literal["json", "jsonl"]


class Movie(TypedDict):
    rank: int
    imdb_id: str | None
    title: str
    rating: float | None
    votes: str | None
    votes_count: int | None
    imdb_url: str | None
    image_url: NotRequired[str | None]
