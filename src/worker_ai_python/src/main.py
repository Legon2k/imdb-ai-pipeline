# --- START OF FILE main.py ---

import asyncio
import json
import os
import httpx
import asyncpg
import redis.asyncio as redis

# System configurations
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
PG_USER = os.getenv("POSTGRES_USER", "imdb_admin")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "supersecretpassword")
PG_DB = os.getenv("POSTGRES_DB", "imdb_ai_db")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
LLM_URL = os.getenv("LLM_API_URL", "http://host.docker.internal:11434/api/generate")
LLM_MODEL = os.getenv("LLM_MODEL_NAME", "gemma:4b")
QUEUE_NAME = "ai_queue"


async def main():
    print(f"AI Worker started. Listening to Redis queue: '{QUEUE_NAME}'...", flush=True)

    # Connect to Redis
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    # Connect to PostgreSQL
    db_pool = await asyncpg.create_pool(
        user=PG_USER, password=PG_PASS, database=PG_DB, host=PG_HOST, port=5432
    )

    # Create persistent HTTP client for LLM
    async with httpx.AsyncClient(timeout=None) as http_client:
        while True:
            try:
                # BRPOP blocks until a message is available (0 = wait forever)
                result = await redis_client.brpop(QUEUE_NAME, timeout=0)
                if not result:
                    continue

                _, message = result
                task = json.loads(message)

                movie_id = task["id"]
                title = task["title"]
                rank = task["rank"]
                rating = task["rating"]

                print(
                    f"[{rank}/250] Generating AI summary for '{title}'...", flush=True
                )

                prompt = f"Write a short, engaging 1-sentence summary for the famous movie '{title}' (IMDB Rating: {rating}). Do not include any intro, just the summary."
                payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False}

                # Request LLM
                response = await http_client.post(LLM_URL, json=payload)
                response.raise_for_status()

                summary = response.json().get("response", "").strip()

                # Update DB to 'completed'
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE movies SET ai_summary = $1, status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $2;",
                        summary,
                        movie_id,
                    )
                print(f"[{rank}/250] Successfully saved summary.", flush=True)

            except Exception as e:
                print(f"! Error processing AI task: {repr(e)}", flush=True)
                await asyncio.sleep(5)  # Delay on error to prevent spamming


if __name__ == "__main__":
    # Disable buffering for Docker logs
    os.environ["PYTHONUNBUFFERED"] = "1"
    asyncio.run(main())
