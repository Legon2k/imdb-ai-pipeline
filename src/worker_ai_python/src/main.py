import asyncio
import os
import httpx
import asyncpg
import redis.asyncio as redis
from redis.exceptions import ResponseError
from pydantic import BaseModel, ValidationError

# System configurations
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
PG_USER = os.getenv("POSTGRES_USER", "imdb_admin")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "supersecretpassword")
PG_DB = os.getenv("POSTGRES_DB", "imdb_ai_db")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
LLM_URL = os.getenv("LLM_API_URL", "http://host.docker.internal:11434/api/generate")
LLM_MODEL = os.getenv("LLM_MODEL_NAME", "gemma:4b")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "600"))
STREAM_NAME = os.getenv("AI_STREAM_NAME", "ai_stream")
CONSUMER_GROUP = os.getenv("AI_CONSUMER_GROUP", "ai_worker")
CONSUMER_NAME = os.getenv("AI_CONSUMER_NAME", "ai-worker-1")
PAYLOAD_FIELD = "payload"


# --- DATA CONTRACT (Pydantic) ---
class AITaskContract(BaseModel):
    """
    Strict data contract for incoming AI tasks from Redis.
    Validates that the JSON payload contains all required fields with correct types.
    """

    id: int
    rank: int
    title: str
    rating: float


async def ensure_consumer_group(redis_client: redis.Redis) -> None:
    try:
        await redis_client.xgroup_create(
            name=STREAM_NAME,
            groupname=CONSUMER_GROUP,
            id="0-0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def read_stream_message(redis_client: redis.Redis):
    result = await redis_client.xreadgroup(
        groupname=CONSUMER_GROUP,
        consumername=CONSUMER_NAME,
        streams={STREAM_NAME: ">"},
        count=1,
        block=5000,
    )
    if not result:
        result = await redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={STREAM_NAME: "0"},
            count=1,
        )
    if not result:
        return None

    _, messages = result[0]
    if not messages:
        return None

    return messages[0]


async def main():
    print(
        f"AI Worker started. Listening to Redis stream: "
        f"'{STREAM_NAME}' as {CONSUMER_GROUP}/{CONSUMER_NAME}...",
        flush=True,
    )

    # Connect to Redis
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    await ensure_consumer_group(redis_client)

    # Connect to PostgreSQL
    db_pool = await asyncpg.create_pool(
        user=PG_USER, password=PG_PASS, database=PG_DB, host=PG_HOST, port=5432
    )

    # Local LLMs can be slow, but each request still needs an upper bound.
    timeout = httpx.Timeout(LLM_TIMEOUT_SECONDS, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        while True:
            task: AITaskContract | None = None
            message_id: str | None = None
            try:
                result = await read_stream_message(redis_client)
                if result is None:
                    continue

                message_id, fields = result
                message = fields.get(PAYLOAD_FIELD)
                if not message:
                    print(
                        f"! Stream entry '{message_id}' is missing the '{PAYLOAD_FIELD}' field.",
                        flush=True,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    continue

                # ---> PYDANTIC VALIDATION <---
                try:
                    # Validate the raw JSON string against our strict contract
                    task = AITaskContract.model_validate_json(message)
                except ValidationError as ve:
                    print(
                        f"! Data Contract Violation in stream '{STREAM_NAME}': {ve}",
                        flush=True,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    continue  # Skip invalid payloads

                print(
                    f"[{task.rank}/250] Generating AI summary for '{task.title}'...",
                    flush=True,
                )

                prompt = f"Write a short, engaging 1-sentence summary for the famous movie '{task.title}' (IMDB Rating: {task.rating}). Do not include any intro, just the summary."
                payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False}

                # Request LLM
                response = await http_client.post(LLM_URL, json=payload)
                response.raise_for_status()

                summary = response.json().get("response", "").strip()
                if not summary:
                    raise RuntimeError("LLM returned an empty summary.")

                # Update DB to 'completed'
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE movies SET ai_summary = $1, status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $2;",
                        summary,
                        task.id,
                    )
                await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                print(f"[{task.rank}/250] Successfully saved summary.", flush=True)

            except Exception as e:
                print(f"! Error processing AI task: {repr(e)}", flush=True)

                # ---> SAFEGUARD / SELF-HEALING <---
                # Revert the status in the database so it's not locked forever as a 'zombie' task
                if task is not None:
                    try:
                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE movies SET status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = $1;",
                                task.id,
                            )
                        print(
                            f"[*] Reverted '{task.title}' back to 'pending' status for future retries.",
                            flush=True,
                        )
                        if message_id is not None:
                            await redis_client.xack(
                                STREAM_NAME, CONSUMER_GROUP, message_id
                            )
                    except Exception as db_err:
                        print(
                            f"! Failed to revert status in DB: {repr(db_err)}",
                            flush=True,
                        )

                await asyncio.sleep(5)  # Delay on error to prevent API spamming


if __name__ == "__main__":
    # Disable buffering for Docker logs
    os.environ["PYTHONUNBUFFERED"] = "1"
    asyncio.run(main())
