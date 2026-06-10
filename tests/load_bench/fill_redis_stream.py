import os
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
import redis


def main():
    # 1. Set up argument parsing
    parser = argparse.ArgumentParser(
        description="Redis Stream Performance Bench Filler"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Optional Redis host override (e.g., 127.0.0.1). If not provided, falls back to .env",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Number of messages to ingest into the stream. Defaults to 1000.",
    )
    args = parser.parse_args()

    # 2. Locate the root directory and .env file relative to this script
    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent.parent
    env_path = root_dir / ".env"

    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        print(
            f"Warning: .env file not found at {env_path}. Using environment/default values."
        )

    # 3. Determine Redis host
    cli_host = args.host
    env_host = os.getenv("REDIS_HOST")

    if cli_host:
        redis_host = cli_host
    elif env_host:
        redis_host = env_host
    else:
        redis_host = "localhost"

    # 4. Extract remaining configurations
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    stream_name = os.getenv("MOVIES_STREAM_NAME", "movies_stream")

    print(
        f"Connecting to Redis at {redis_host}:{redis_port}, Target Stream: {stream_name}"
    )

    # 5. Initialize Redis connection and pipeline
    try:
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=30.0,  # Increased to 30s to withstand WSL2 disk latency
            socket_timeout=30.0,  # Increased to 30s to prevent socket timeouts
        )
        pipe = r.pipeline()
    except Exception as e:
        print(f"Failed to initialize Redis client: {e}")
        return

    # 6. Define a realistic movie JSON payload
    movie_payload = {
        "rank": 1,
        "imdb_id": "tt0111161",
        "title": "The Shawshank Redemption",
        "rating": 9.3,
        "votes": "2.9M",
        "votes_count": 2900000,
        "imdb_url": "https://www.imdb.com/title/tt0111161/",
        "image_url": "https://m.media-amazon.com/images/M/MV5BNDE3ODcxNzMtY2YzZC00NmNlLWJiNDMtZDViZWM2MzcwM2IwXkEyXkFqcGdeQXVyNDk3OD9kMTQ@._V1_.jpg",
    }
    json_payload = json.dumps(movie_payload)

    # 7. Define benchmark parameters from CLI arguments
    total_messages = args.count

    # Dynamically adjust batch size so it doesn't exceed the total message count
    batch_size = min(1000, total_messages)

    print(
        f"Starting data ingestion of {total_messages} messages into Redis Stream '{stream_name}'..."
    )

    try:
        for i in range(1, total_messages + 1):
            pipe.xadd(stream_name, {"payload": json_payload})

            # Flush the batch to Redis
            if i % batch_size == 0:
                pipe.execute()
                print(f"Ingested {i} out of {total_messages} messages...")

        # Flush any remaining messages left in the pipeline buffer
        if len(pipe):
            pipe.execute()

        print(
            f"\nSuccess! Stream '{stream_name}' has been successfully populated with {total_messages} messages."
        )

    except redis.exceptions.ConnectionError:
        print(
            f"Connection Error: Could not connect to Redis at {redis_host}:{redis_port}."
        )
    except Exception as e:
        print(f"An unexpected error occurred during ingestion: {e}")


if __name__ == "__main__":
    main()
