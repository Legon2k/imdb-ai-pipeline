import io
import json
import os
from contextlib import asynccontextmanager
from typing import List, Dict, Any
from datetime import datetime

import asyncpg
import pandas as pd
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Global variables to hold our connections
db_pool = None
redis_client = None


# --- API DATA CONTRACTS (Pydantic) ---
class MovieResponse(BaseModel):
    """Data contract for the API response."""

    id: int
    imdb_id: str
    rank: int
    title: str
    rating: float
    votes: str
    status: str
    updated_at: datetime


class EnrichmentResponse(BaseModel):
    message: str
    queued_tasks: int


class RecoverResponse(BaseModel):
    message: str
    recovered_movies: List[Dict[str, Any]]


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
            port=os.getenv("POSTGRES_PORT", 5432),
        )

        # Initialize Redis connection
        redis_client = redis.Redis(
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
    description="API Gateway for accessing processed IMDB movie data, triggering AI tasks, and self-healing.",
    version="3.0.0",
    lifespan=lifespan,
)


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
    response_model=List[MovieResponse],
)
async def get_movies(limit: int = 50, offset: int = 0):
    """
    Retrieves a list of processed movies from the PostgreSQL database.
    """
    if not db_pool:
        raise HTTPException(
            status_code=500, detail="Database connection is not initialized."
        )

    query = """
        SELECT id, imdb_id, rank, title, rating, votes, status, updated_at 
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
        raise HTTPException(
            status_code=500, detail="Database connection is not initialized."
        )

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
        raise HTTPException(
            status_code=500, detail="Database connection is not initialized."
        )

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
    and queues them in Redis for the AI background worker.
    Returns HTTP 202 Accepted instantly.
    """
    if not db_pool or not redis_client:
        raise HTTPException(
            status_code=500, detail="Infrastructure connections are not ready."
        )

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
    async with db_pool.acquire() as connection:
        async with connection.transaction():
            pending_movies = await connection.fetch(lock_query, limit)

    if not pending_movies:
        return {"message": "No pending movies found to enrich.", "queued_tasks": 0}

    tasks = [
        json.dumps(
            {
                "id": movie["id"],
                "rank": movie["rank"],
                "title": movie["title"],
                "rating": float(movie["rating"]),
            }
        )
        for movie in pending_movies
    ]
    movie_ids = [movie["id"] for movie in pending_movies]

    try:
        await redis_client.lpush("ai_queue", *tasks)
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
            detail="Failed to queue AI enrichment tasks. Movie locks were reverted.",
        ) from exc

    return {
        "message": "AI enrichment tasks successfully added to the background queue.",
        "queued_tasks": len(tasks),
    }
