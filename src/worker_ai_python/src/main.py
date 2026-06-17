# File: worker_ai/main.py
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

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
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
POSTGRES_USER = os.getenv("POSTGRES_USER", "imdb_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "supersecretpassword")
POSTGRES_DB = os.getenv("POSTGRES_DB", "imdb_ai_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
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


# --- OPENTELEMETRY TRACING INITIALIZATION ---
def setup_otel(service_name: str = "imdb-ai-worker") -> trace.Tracer:
    """Configures OpenTelemetry TracerProvider and OTLP Exporter pointing to Alloy [1.1, 1.2.7]."""
    try:
        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        logging.info(f"OpenTelemetry successfully initialized. Exporting to {otlp_endpoint}")
        return trace.get_tracer(service_name)
    except Exception as exc:
        logging.warning(f"Failed to initialize OpenTelemetry. Falling back to No-Op: {exc}")
        return trace.get_noop_tracer()


# --- STRUCTURED JSON LOGGING WITH OTel ---
class WorkerJsonFormatter(logging.Formatter):
    """
    Structured JSON formatter for the AI Worker.
    Outputs logs in JSON format and automatically injects active OTel trace correlation IDs [1.5].
    """

    def __init__(self, service_name: str = "imdb-ai-worker"):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        log_record = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service_name": self.service_name,
            "version": APP_VERSION,
        }

        # Automatically extract trace correlation metadata if an active OTel span exists [1.5]
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context() if current_span else None
        if span_context and span_context.is_valid:
            log_record["traceID"] = trace.format_trace_id(span_context.trace_id)
            log_record["spanID"] = trace.format_span_id(span_context.span_id)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_worker_logging(service_name: str = "imdb-ai-worker", level: str | int = logging.INFO):
    """Configures the root logger to output JSON to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(WorkerJsonFormatter(service_name))

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


# Initialize JSON logging on application startup
setup_worker_logging(service_name="imdb-ai-worker", level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger("imdb_ai_worker")

# Initialize OpenTelemetry Tracer
tracer = setup_otel(service_name="imdb-ai-worker")


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
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        host=POSTGRES_HOST,
        port=5432,
    )
    LOGGER.info("event=postgres_connected host=%s port=%s database=%s", POSTGRES_HOST, 5432, POSTGRES_DB)

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
                        "event=message_missing_payload stream=%s group=%s consumer=%s message_id=%s field=%s",
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        message_id,
                        PAYLOAD_FIELD,
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    continue

                # --- EXTRACT TRACEPARENT FROM PAYLOAD ---
                traceparent = None
                sanitized_message = message
                try:
                    raw_json = json.loads(message)
                    traceparent = raw_json.get("traceparent")

                    # Sanitize the message: remove traceparent to prevent strict Pydantic validation errors [2]
                    if "traceparent" in raw_json:
                        del raw_json["traceparent"]
                        sanitized_message = json.dumps(raw_json)
                except Exception:
                    pass

                # Extract parent context natively using OpenTelemetry propagator [1.1]
                carrier = {"traceparent": traceparent} if traceparent else {}
                parent_context = TraceContextTextMapPropagator().extract(carrier=carrier)

                # Start an active span linked to the parent trace [1.3]
                # Any logging called inside this block automatically gets traceID and spanID [1.5]
                with tracer.start_as_current_span("ProcessAITask", context=parent_context) as span:
                    try:
                        # ---> PYDANTIC VALIDATION <---
                        try:
                            # Validate sanitized JSON against strict contract [2]
                            task = AITaskPayload.model_validate_json(sanitized_message)
                        except ValidationError as ve:
                            AI_TASKS_PROCESSED_TOTAL.labels(status="contract_violation").inc()
                            LOGGER.warning(
                                "event=contract_violation stream=%s group=%s consumer=%s message_id=%s error=%r",
                                STREAM_NAME,
                                CONSUMER_GROUP,
                                CONSUMER_NAME,
                                message_id,
                                ve,
                            )
                            await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                            continue  # Skip invalid payloads

                        span.set_attribute("movie.id", task.id)
                        span.set_attribute("movie.title", task.title)

                        LOGGER.info(
                            "event=task_started stream=%s group=%s consumer=%s \
                                message_id=%s movie_id=%s rank=%s title=%r",
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

                        span.set_attribute("llm.duration_ms", llm_duration_ms)
                        span.set_attribute("llm.summary_length", len(summary))

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
                        LOGGER.info(
                            "event=task_completed stream=%s group=%s consumer=%s message_id=%s \
                                movie_id=%s rank=%s llm_duration_ms=%s summary_chars=%s",
                            STREAM_NAME,
                            CONSUMER_GROUP,
                            CONSUMER_NAME,
                            message_id,
                            task.id,
                            task.rank,
                            llm_duration_ms,
                            len(summary),
                        )

                    except Exception as inside_exc:
                        # Record exception inside active span context for Tempo representation [1.3, 1.4]
                        span.record_exception(inside_exc)
                        span.set_status(trace.StatusCode.ERROR, str(inside_exc))

                        AI_TASKS_PROCESSED_TOTAL.labels(status="failed").inc()
                        LOGGER.exception(
                            "event=task_failed stream=%s group=%s consumer=%s message_id=%s movie_id=%s error=%r",
                            STREAM_NAME,
                            CONSUMER_GROUP,
                            CONSUMER_NAME,
                            message_id,
                            task.id if task is not None else None,
                            inside_exc,
                        )

                        # ---> SAFEGUARD / SELF-HEALING <---
                        if task is not None:
                            try:
                                async with db_pool.acquire() as conn:
                                    await conn.execute(
                                        "UPDATE movies SET status = 'pending', \
                                            updated_at = CURRENT_TIMESTAMP WHERE id = $1;",
                                        task.id,
                                    )
                                LOGGER.info(
                                    "event=task_reverted \
                                        movie_id=%s rank=%s title=%r status=pending",
                                    task.id,
                                    task.rank,
                                    task.title,
                                )
                                if message_id is not None:
                                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                            except Exception as db_err:
                                LOGGER.exception(
                                    "event=task_revert_failed movie_id=%s rank=%s error=%r",
                                    task.id,
                                    task.rank,
                                    db_err,
                                )

                        await asyncio.sleep(5)  # Delay on error to prevent API spamming

            except Exception as outer_exc:
                # Catch-all block for errors occurring outside
                # active task scope (e.g. Redis Stream failures)
                AI_TASKS_PROCESSED_TOTAL.labels(status="failed").inc()
                LOGGER.exception("event=outer_loop_failed error=%r", outer_exc)
                await asyncio.sleep(5)


if __name__ == "__main__":
    os.environ["PYTHONUNBUFFERED"] = "1"
    asyncio.run(main())
