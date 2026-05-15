import json
import logging
import os
from typing import Any

import redis  # type: ignore[import]

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class RedisPublisher:
    def __init__(self, queue_name: str = "movies_queue"):
        self.queue_name = queue_name

        # Fetch host and port from environment variables (Docker injects these via .env)
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))

        try:
            self.client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,  # Automatically decode bytes to strings
            )
            # Ping to verify the connection is alive
            self.client.ping()
            logger.info(f"Successfully connected to Redis at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def publish_movie(self, movie_data: dict[str, Any]) -> bool:
        """
        Publishes a dictionary with movie data to the Redis queue.

        Args:
            movie_data: Dictionary containing scraped movie details.
        Returns:
            bool: True if successfully published, False otherwise.
        """
        try:
            json_payload = json.dumps(movie_data)

            # LPUSH adds the payload to the head of the list (acting as a queue)
            self.client.lpush(self.queue_name, json_payload)
            logger.info(
                f"Successfully published movie to queue: {movie_data.get('title', 'Unknown')}"
            )
            return True
        except Exception as e:
            logger.error(f"Error publishing movie {movie_data.get('title', 'Unknown')}: {e}")
            return False
