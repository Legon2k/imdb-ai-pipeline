import asyncio
import logging
import os
import sys
from time import perf_counter

import httpx
import asyncpg
import redis.asyncio as redis
from redis.exceptions import ResponseError
from pydantic import ValidationError

# Add parent directory to path to import shared contracts
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))
from contracts import AITaskPayload

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

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("imdb_ai_worker")


async def ensure_consumer_group(redis_client: redis.Redis) -> None:
    try:
        await redis_client.xgroup_create(
            name=STREAM_NAME,
            groupname=CONSUMER_GROUP,
            id="0-0",
            mkstream=True,
        )
        LOGGER.info(
            "event=consumer_group_created stream=%s group=%s",
            STREAM_NAME,
            CONSUMER_GROUP,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        LOGGER.info(
            "event=consumer_group_exists stream=%s group=%s",
            STREAM_NAME,
            CONSUMER_GROUP,
        )


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
    LOGGER.info(
        "event=worker_started stream=%s group=%s consumer=%s model=%s timeout_seconds=%s",
        STREAM_NAME,
        CONSUMER_GROUP,
        CONSUMER_NAME,
        LLM_MODEL,
        LLM_TIMEOUT_SECONDS,
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
            task: AITaskPayload | None = None
            message_id: str | None = None
            try:
                result = await read_stream_message(redis_client)
                if result is None:
                    continue

                message_id, fields = result
                message = fields.get(PAYLOAD_FIELD)
                if not message:
                    LOGGER.warning(
                        "event=message_missing_payload stream=%s group=%s consumer=%s message_id=%s field=%s",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        message_id,
                        PAYLOAD_FIELD,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    LOGGER.info(
                        "event=message_acked stream=%s group=%s message_id=%s reason=missing_payload",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        message_id,
                    )
                    continue

                # ---> PYDANTIC VALIDATION <---
                try:
                    # Validate the raw JSON string against our strict contract (from contracts/schemas.json)
                    task = AITaskPayload.model_validate_json(message)
                except ValidationError as ve:
                    LOGGER.warning(
                        "event=contract_violation stream=%s group=%s consumer=%s message_id=%s error=%r",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        message_id,
                        ve,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    LOGGER.info(
                        "event=message_acked stream=%s group=%s message_id=%s reason=contract_violation",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        message_id,
                    )
                    continue  # Skip invalid payloads

                LOGGER.info(
                    "event=task_started stream=%s group=%s consumer=%s message_id=%s movie_id=%s rank=%s title=%r",
                    STREAM_NAME,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    message_id,
                    task.id,
                    task.rank,
                    task.title,
                )

                prompt = f"Write a short, engaging 1-sentence summary for the famous movie '{task.title}' (IMDB Rating: {task.rating}). Do not include any intro, just the summary."
                payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False}

                # Request LLM
                started_at = perf_counter()
                response = await http_client.post(LLM_URL, json=payload)
                response.raise_for_status()
                llm_duration_ms = round((perf_counter() - started_at) * 1000, 2)

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
                LOGGER.info(
                    "event=task_completed stream=%s group=%s consumer=%s message_id=%s movie_id=%s rank=%s llm_duration_ms=%s summary_chars=%s",
                    STREAM_NAME,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    message_id,
                    task.id,
                    task.rank,
                    llm_duration_ms,
                    len(summary),
                )

            except Exception as e:
                LOGGER.exception(
                    "event=task_failed stream=%s group=%s consumer=%s message_id=%s movie_id=%s error=%r",
                    STREAM_NAME,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    message_id,
                    task.id if task is not None else None,
                    e,
                )

                # ---> SAFEGUARD / SELF-HEALING <---
                # Revert the status in the database so it's not locked forever as a 'zombie' task
                if task is not None:
                    try:
                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE movies SET status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE id = $1;",
                                task.id,
                            )
                        LOGGER.info(
                            "event=task_reverted movie_id=%s rank=%s title=%r status=pending",
                            task.id,
                            task.rank,
                            task.title,
                        )
                        if message_id is not None:
                            await redis_client.xack(
                                STREAM_NAME, CONSUMER_GROUP, message_id
                            )
                            LOGGER.info(
                                "event=message_acked stream=%s group=%s message_id=%s reason=task_reverted",
                                STREAM_NAME,
                                CONSUMER_GROUP,
                                message_id,
                            )
                    except Exception as db_err:
                        LOGGER.exception(
                            "event=task_revert_failed movie_id=%s rank=%s error=%r",
                            task.id,
                            task.rank,
                            db_err,
                        )

                await asyncio.sleep(5)  # Delay on error to prevent API spamming


if __name__ == "__main__":
    # Disable buffering for Docker logs
    os.environ["PYTHONUNBUFFERED"] = "1"
    asyncio.run(main())
