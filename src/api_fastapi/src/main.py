from pydantic import BaseModel
from datetime import datetime

import io
import json
import os
from contextlib import asynccontextmanager
from typing import List

import asyncpg
import pandas as pd
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

# Global variables to hold our connections
db_pool = None
redis_client = None


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
    description="API Gateway for accessing processed IMDB movie data and triggering AI tasks.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get(
    "/movies",
    summary="Get all movies",
    tags=["Movies"],
    response_model=List[MovieResponse],
)
async def get_movies(limit: int = 50, offset: int = 0):
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
    "/movies/enrich",
    status_code=202,
    summary="Trigger AI Enrichment",
    tags=["AI Enrichment"],
    response_model=EnrichmentResponse,
)
async def enrich_movies(limit: int = 5):
    """
    Finds 'pending' movies and queues them in Redis for the AI background worker.
    Returns HTTP 202 Accepted instantly.
    """
    if not db_pool or not redis_client:
        raise HTTPException(
            status_code=500, detail="Infrastructure connections are not ready."
        )

    # 1. Fetch pending movies
    select_query = "SELECT id, rank, title, rating FROM movies WHERE status = 'pending' ORDER BY rank ASC LIMIT $1;"
    async with db_pool.acquire() as connection:
        pending_movies = await connection.fetch(select_query, limit)

    if not pending_movies:
        return {"message": "No pending movies found.", "queued_tasks": 0}

    queued_count = 0
    async with db_pool.acquire() as connection:
        for movie in pending_movies:
            # 2. Build the task payload
            task = {
                "id": movie["id"],
                "rank": movie["rank"],
                "title": movie["title"],
                "rating": float(
                    movie["rating"]
                ),  # <--- explicitly cast Decimal to float
            }

            # 3. Push to Redis queue
            await redis_client.lpush("ai_queue", json.dumps(task))

            # 4. Update status to 'processing' so it doesn't get queued twice
            await connection.execute(
                "UPDATE movies SET status = 'processing' WHERE id = $1;", movie["id"]
            )
            queued_count += 1

    return {
        "message": "AI enrichment tasks successfully added to the background queue.",
        "queued_tasks": queued_count,
    }
