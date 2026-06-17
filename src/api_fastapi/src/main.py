import io
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal

import asyncpg
import pandas as pd
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
from contracts import DatabaseMovie

# Retrieve the application version from environment variables (Runtime ENV)
APP_VERSION = os.getenv("APP_VERSION", "0.0.0-dev")


# --- OPENTELEMETRY TRACING INITIALIZATION ---
def setup_otel(app: FastAPI, service_name: str = "imdb-api") -> trace.Tracer:
    """Configures OpenTelemetry TracerProvider and OTLP Exporter pointing to Alloy."""
    try:
        # Check if the app is a mocked object (common in unit tests / mocks)
        if not hasattr(app, "build_middleware_stack"):
            logging.warning(
                "FastAPI app instance lacks standard methods. "
                "Skipping OTel instrumentation (Testing/Mock environment detected)."
            )
            # Default to standard tracer, which automatically acts as No-Op if SDK is not set up
            return trace.get_tracer(service_name)

        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)

        # Point to Alloy gRPC receiver inside Docker network
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument FastAPI routes [1.1]
        FastAPIInstrumentor.instrument_app(app)

        logging.info(f"OpenTelemetry successfully initialized. Exporting to {otlp_endpoint}")
        return trace.get_tracer(service_name)
    except Exception as exc:
        logging.warning(f"Failed to initialize OpenTelemetry. Falling back to No-Op: {exc}")
        # Standard OTel fallback: get_tracer behaves as No-Op if provider was not registered
        return trace.get_tracer(service_name)


def get_traceparent() -> str:
    """Helper to extract active OTel traceparent from current span context."""
    carrier = {}
    TraceContextTextMapPropagator().inject(carrier)
    return carrier.get("traceparent", "")


# --- STRUCTURED JSON LOGGING SETUP ---
class ApiJsonFormatter(logging.Formatter):
    """
    Structured JSON formatter for the FastAPI API Gateway.
    Converts logs and injects OpenTelemetry metadata if an active trace exists [1.1, 1.5].
    """

    def __init__(self, service_name: str = "imdb-api"):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        message = record.getMessage()

        log_record = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "service_name": self.service_name,
            "version": APP_VERSION,
        }

        # Inject trace correlation IDs if OpenTelemetry is active [1.5]
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context() if current_span else None
        if span_context and span_context.is_valid:
            log_record["traceID"] = trace.format_trace_id(span_context.trace_id)
            log_record["spanID"] = trace.format_span_id(span_context.span_id)

        # Extract HTTP metadata if it's a uvicorn access log [1.1]
        if record.name == "uvicorn.access" and len(record.args) >= 5:
            log_record["http"] = {
                "client_address": record.args[0],
                "method": record.args[1],
                "path": record.args[2],
                "status_code": record.args[4],
            }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_api_logging(service_name: str = "imdb-api", level: int = logging.INFO):
    """Configures root and uvicorn loggers to use our custom JSON formatter [1.1]."""
    formatter = ApiJsonFormatter(service_name)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure Root Logger
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Intercept and configure Uvicorn loggers to enforce JSON output [1.1]
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False  # Avoid log duplication in root logger


# Initialize logging and log level
RAW_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
LOG_LEVEL = getattr(logging, RAW_LOG_LEVEL, logging.INFO)
setup_api_logging(service_name="imdb-api", level=LOG_LEVEL)


# Global variables to hold our connections
db_pool = None
redis_client = None
AI_STREAM_NAME = os.getenv("AI_STREAM_NAME", "ai_stream")
AI_STREAM_MAXLEN = int(os.getenv("AI_STREAM_MAXLEN", "1000"))


# --- API DATA CONTRACTS (Pydantic) ---
class MovieResponse(DatabaseMovie):
    """
    API response model for GET /movies.
    Extends DatabaseMovie to match database schema.
    """

    pass


class EnrichmentResponse(BaseModel):
    message: str
    queued_tasks: int


class ScrapeResponse(BaseModel):
    message: str


class RecoverResponse(BaseModel):
    message: str
    recovered_movies: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    postgres: str
    redis: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager to handle database and Redis connections.
    """
    global db_pool, redis_client
    try:
        # Initialize PostgreSQL pool
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "imdb_admin"),
            password=os.getenv("POSTGRES_PASSWORD", "supersecretpassword"),
            database=os.getenv("POSTGRES_DB", "imdb_ai_db"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
        )

        # Initialize Redis connection
        redis_client = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True,
        )
        yield
    finally:
        if db_pool:
            await db_pool.close()
        if redis_client:
            await redis_client.aclose()


app = FastAPI(
    title="IMDB AI Pipeline API",
    description=(
        "API Gateway for accessing processed IMDB movie data, "
        "triggering AI tasks, and self-healing."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)

# 1. Initialize OpenTelemetry after FastAPI instantiation [1.1]
tracer = setup_otel(app, service_name="imdb-api")


@app.get(
    "/health",
    summary="API liveness check",
    tags=["Health"],
    response_model=HealthResponse,
)
async def health_check():
    """
    Reports whether the API process is running.
    """
    return {"status": "ok"}


@app.get(
    "/ready",
    summary="API readiness check",
    tags=["Health"],
    response_model=ReadinessResponse,
)
async def readiness_check():
    """
    Verifies that the API can reach its required infrastructure dependencies.
    """
    if not db_pool or not redis_client:
        raise HTTPException(
            status_code=503, detail="Infrastructure connections are not initialized."
        )

    try:
        async with db_pool.acquire() as connection:
            await connection.fetchval("SELECT 1;")
        await redis_client.ping()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Infrastructure dependency check failed: {exc!r}"
        ) from exc

    return {"status": "ready", "postgres": "ok", "redis": "ok"}


@app.get(
    "/movies",
    summary="Get all movies",
    tags=["Movies"],
    response_model=list[MovieResponse],
)
async def get_movies(limit: int = 50, offset: int = 0):
    """
    Retrieves a list of processed movies from the PostgreSQL database.
    """
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database connection is not initialized.")

    query = """
        SELECT
            id, imdb_id, rank, title, rating, votes, image_url, ai_summary,
            status, created_at, updated_at
        FROM movies ORDER BY rank ASC LIMIT $1 OFFSET $2;
    """
    async with db_pool.acquire() as connection:
        records = await connection.fetch(query, limit, offset)

    return [dict(record) for record in records]


@app.get("/movies/export", summary="Export movies to Excel", tags=["Export"])
async def export_movies_to_excel():
    """
    Generates an Excel (.xlsx) file on the fly containing all scraped movies,
    including the AI-generated summaries. Perfect for business clients.
    """
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database connection is not initialized.")

    query = "SELECT rank, title, rating, votes, status, ai_summary FROM movies ORDER BY rank ASC;"
    async with db_pool.acquire() as connection:
        records = await connection.fetch(query)

    if not records:
        raise HTTPException(status_code=404, detail="No movies found.")

    df = pd.DataFrame([dict(r) for r in records])
    df.rename(
        columns={
            "rank": "Rank",
            "title": "Movie Title",
            "rating": "IMDB Rating",
            "votes": "Total Votes",
            "status": "AI Status",
            "ai_summary": "AI Generated Summary",
        },
        inplace=True,
    )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Top 250 Movies")

    output.seek(0)
    return StreamingResponse(
        output,
        headers={"Content-Disposition": 'attachment; filename="imdb_top_movies.xlsx"'},
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post(
    "/movies/recover",
    summary="Recover stuck processing tasks",
    tags=["System Maintenance"],
    response_model=RecoverResponse,
)
async def recover_stuck_movies(stuck_minutes: int = Query(default=10, ge=1, le=1440)):
    """
    Scans the database for movies that have been in the 'processing' state
    for longer than the specified time (default 10 minutes) and resets them
    to 'pending' so they can be picked up again by the AI enrichment trigger.
    """
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database connection is not initialized.")

    recover_query = """
        UPDATE movies 
        SET status = 'pending', updated_at = CURRENT_TIMESTAMP
        WHERE status = 'processing' 
        AND updated_at < CURRENT_TIMESTAMP - make_interval(mins => $1)
        RETURNING id, title;
    """

    async with db_pool.acquire() as connection:
        recovered_records = await connection.fetch(recover_query, stuck_minutes)

    recovered_count = len(recovered_records)

    return {
        "message": f"Successfully recovered {recovered_count} stuck tasks.",
        "recovered_movies": [dict(r) for r in recovered_records],
    }


@app.post(
    "/movies/enrich",
    status_code=202,
    summary="Trigger AI Enrichment (Async)",
    tags=["AI Enrichment"],
    response_model=EnrichmentResponse,
)
async def enrich_movies(limit: int = Query(default=5, ge=1, le=250)):
    """
    Finds 'pending' movies, updates their status to 'processing' to lock them,
    and publishes them to Redis Streams for the AI background worker.
    Returns HTTP 202 Accepted instantly.
    """
    if not db_pool or not redis_client:
        raise HTTPException(status_code=500, detail="Infrastructure connections are not ready.")

    lock_query = """
        WITH selected AS (
            SELECT id, rank, title, rating
            FROM movies
            WHERE status = 'pending'
            ORDER BY rank ASC
            LIMIT $1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE movies AS m
        SET status = 'processing', updated_at = CURRENT_TIMESTAMP
        FROM selected
        WHERE m.id = selected.id
        RETURNING m.id, m.rank, m.title, m.rating;
    """
    async with db_pool.acquire() as connection, connection.transaction():
        pending_movies = await connection.fetch(lock_query, limit)

    if not pending_movies:
        return {"message": "No pending movies found to enrich.", "queued_tasks": 0}

    # Extract the current active traceparent from OpenTelemetry [1.1]
    traceparent = get_traceparent()

    tasks = [
        {
            "payload": json.dumps(
                {
                    "id": movie["id"],
                    "rank": movie["rank"],
                    "title": movie["title"],
                    "rating": float(movie["rating"]),
                    "traceparent": traceparent,  # <--- Trace context injected
                }
            )
        }
        for movie in pending_movies
    ]
    movie_ids = [movie["id"] for movie in pending_movies]

    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            for task in tasks:
                pipe.xadd(
                    AI_STREAM_NAME,
                    task,
                    maxlen=AI_STREAM_MAXLEN,
                    approximate=True,
                )
            await pipe.execute()
    except Exception as exc:
        async with db_pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE movies
                SET status = 'pending', updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY($1::int[]);
                """,
                movie_ids,
            )
        raise HTTPException(
            status_code=503,
            detail="Failed to publish AI enrichment tasks. Movie locks were reverted.",
        ) from exc

    return {
        "message": "AI enrichment tasks successfully added to the background stream.",
        "queued_tasks": len(tasks),
    }


CONTAINER_SOCKET_PATH = os.getenv("CONTAINER_SOCKET_PATH", "unix:///var/run/docker.sock")


@app.post(
    "/movies/scrape",
    status_code=202,
    summary="Trigger Movie Scraping (Async)",
    tags=["Scraping"],
    response_model=ScrapeResponse,
)
async def trigger_scraping(chart: Literal["top", "moviemeter", "toptv", "tvmeter"] = "moviemeter"):
    """
    Triggers the scraping of IMDb movies for the specified chart.
    Returns HTTP 202 Accepted instantly.
    """
    logging.info(f"Using container socket: {CONTAINER_SOCKET_PATH}")

    # Extract active traceparent from current span to inject into container environment [1.1]
    traceparent = get_traceparent()
    redis_host = os.getenv("REDIS_HOST", "imdb_redis")

    from docker import DockerClient

    client = DockerClient(base_url=CONTAINER_SOCKET_PATH)

    client.containers.run(
        image="imdb-ai-pipeline-scraper:latest",
        command=[f"--chart={chart}"],
        remove=True,
        detach=True,
        network="imdb-ai-pipeline_internal_network",
        environment={
            "REDIS_HOST": redis_host,
            "SCRAPER_CHART": chart,
            "SCRAPER_TRACEPARENT": traceparent,  # <--- Trace context injected [1.1]
        },
    )

    return {"message": "Scraping triggered."}
