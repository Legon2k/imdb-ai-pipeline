import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from time import perf_counter

import asyncpg
import httpx
import redis.asyncio as redis
from prometheus_client import Counter, Histogram, start_http_server
from pydantic import ValidationError
from redis.exceptions import ResponseError

# Add src directory to path to import shared contracts
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
from contracts import AITaskPayload

# Retrieve the application version from environment variables (Runtime ENV)
APP_VERSION = os.getenv("APP_VERSION", "0.0.0-dev")

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
METRICS_PORT = int(os.getenv("METRICS_PORT", "8001"))

AI_TASKS_PROCESSED_TOTAL = Counter(
    "ai_tasks_processed_total",
    "Total AI enrichment tasks processed by outcome.",
    ["status"],
)
LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds",
    "Local LLM generation latency in seconds.",
    buckets=(5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)
LLM_SUMMARY_CHARACTERS = Histogram(
    "llm_summary_characters",
    "Character length of successful local LLM summaries.",
    buckets=(50, 100, 150, 200, 300, 500),
)


# --- STRUCTURED JSON LOGGING WITH CONTEXT ADAPTER ---
class WorkerJsonFormatter(logging.Formatter):
    """
    Structured JSON formatter for the AI Worker.
    Outputs logs in JSON format with standard metadata and traceID injection [1.5].
    """

    def __init__(self, service_name: str = "imdb-ai-worker"):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        log_record = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service_name": self.service_name,
            "version": APP_VERSION,
        }

        # Inject trace correlation metadata if appended via LoggerAdapter [1.5]
        if hasattr(record, "traceID"):
            log_record["traceID"] = record.traceID
        if hasattr(record, "spanID"):
            log_record["spanID"] = record.spanID

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


class TraceLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter to dynamically inject trace context into log record extra fields [3].
    """

    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        if self.extra:
            extra.update(self.extra)
        return msg, kwargs


def setup_worker_logging(service_name: str = "imdb-ai-worker", level: str | int = logging.INFO):
    """Configures the root logger to output JSON to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(WorkerJsonFormatter(service_name))

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def parse_traceparent(traceparent: str) -> tuple[str | None, str | None]:
    """
    Safely parses W3C traceparent headers to extract traceID and spanID [1].
    Format: version-trace_id-parent_id-trace_flags
    Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
    """
    if not traceparent:
        return None, None
    parts = traceparent.split("-")
    if len(parts) >= 3 and len(parts[1]) == 32 and len(parts[2]) == 16:
        return parts[1], parts[2]
    return None, None


# Initialize JSON logging on application startup
setup_worker_logging(service_name="imdb-ai-worker", level=os.getenv("LOG_LEVEL", "INFO"))
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
    LOGGER.info(f"IMDb AI Worker starting up v{APP_VERSION}. Connecting to Redis and PostgreSQL...")
    start_http_server(METRICS_PORT)
    LOGGER.info("event=metrics_server_started port=%s path=/metrics", METRICS_PORT)

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
    LOGGER.info("event=redis_connected host=%s port=%s", REDIS_HOST, REDIS_PORT)

    # Connect to PostgreSQL
    db_pool = await asyncpg.create_pool(
        user=PG_USER, password=PG_PASS, database=PG_DB, host=PG_HOST, port=5432
    )
    LOGGER.info("event=postgres_connected host=%s port=%s database=%s", PG_HOST, 5432, PG_DB)

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
                    AI_TASKS_PROCESSED_TOTAL.labels(status="missing_payload").inc()
                    LOGGER.warning(
                        "event=message_missing_payload stream=%s group=%s consumer=%s "
                        "message_id=%s field=%s",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        message_id,
                        PAYLOAD_FIELD,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    LOGGER.info(
                        "event=message_acked stream=%s group=%s message_id=%s "
                        "reason=missing_payload",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        message_id,
                    )
                    continue

                # ---> PRE-VALIDATION TRACE CONTEXT EXTRACTION <---
                # Extract trace context early so that even validation
                # failures contain trace IDs [1.3]
                traceparent = None
                try:
                    raw_json = json.loads(message)
                    traceparent = raw_json.get("traceparent")
                except Exception:
                    pass

                trace_id, span_id = parse_traceparent(traceparent)
                task_logger = TraceLoggerAdapter(
                    LOGGER, {"traceID": trace_id, "spanID": span_id} if trace_id else {}
                )
                # ------------------------------------------------

                # ---> PYDANTIC VALIDATION <---
                try:
                    # Validate raw JSON against strict contract
                    task = AITaskPayload.model_validate_json(message)
                except ValidationError as ve:
                    AI_TASKS_PROCESSED_TOTAL.labels(status="contract_violation").inc()
                    task_logger.warning(
                        "event=contract_violation stream=%s group=%s consumer=%s "
                        "message_id=%s error=%r",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        message_id,
                        ve,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    task_logger.info(
                        "event=message_acked stream=%s group=%s message_id=%s "
                        "reason=contract_violation",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        message_id,
                    )
                    continue  # Skip invalid payloads

                task_logger.info(
                    "event=task_started stream=%s group=%s consumer=%s message_id=%s "
                    "movie_id=%s rank=%s title=%r",
                    STREAM_NAME,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    message_id,
                    task.id,
                    task.rank,
                    task.title,
                )

                prompt = (
                    f"Write a 1-sentence summary for the movie '{task.title}' "
                    f"(IMDB Rating: {task.rating}). No intro, just the summary."
                )
                payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False}

                # Request LLM
                started_at = perf_counter()
                response = await http_client.post(LLM_URL, json=payload)
                response.raise_for_status()
                llm_duration_seconds = perf_counter() - started_at
                LLM_REQUEST_DURATION_SECONDS.observe(llm_duration_seconds)
                llm_duration_ms = round(llm_duration_seconds * 1000, 2)

                summary = response.json().get("response", "").strip()
                if not summary:
                    raise RuntimeError("LLM returned an empty summary.")
                LLM_SUMMARY_CHARACTERS.observe(len(summary))

                # Update DB to 'completed'
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE movies SET ai_summary = $1, status = 'completed', "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = $2;",
                        summary,
                        task.id,
                    )
                await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                AI_TASKS_PROCESSED_TOTAL.labels(status="completed").inc()
                task_logger.info(
                    "event=task_completed stream=%s group=%s consumer=%s message_id=%s "
                    "movie_id=%s rank=%s llm_duration_ms=%s summary_chars=%s",
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
                AI_TASKS_PROCESSED_TOTAL.labels(status="failed").inc()
                # Determine safe fallback logger inside exception catch
                logger_to_use = task_logger if "task_logger" in locals() else LOGGER
                logger_to_use.exception(
                    "event=task_failed stream=%s group=%s consumer=%s message_id=%s "
                    "movie_id=%s error=%r",
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
                                "UPDATE movies SET status = 'pending', "
                                "updated_at = CURRENT_TIMESTAMP WHERE id = $1;",
                                task.id,
                            )
                        logger_to_use.info(
                            "event=task_reverted movie_id=%s rank=%s title=%r status=pending",
                            task.id,
                            task.rank,
                            task.title,
                        )
                        if message_id is not None:
                            await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                            logger_to_use.info(
                                "event=message_acked stream=%s group=%s message_id=%s "
                                "reason=task_reverted",
                                STREAM_NAME,
                                CONSUMER_GROUP,
                                message_id,
                            )
                    except Exception as db_err:
                        logger_to_use.exception(
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
