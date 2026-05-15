# --- START OF FILE main.py ---

import io
import os
from contextlib import asynccontextmanager
from typing import List, Dict, Any

import asyncpg
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

# Global variable to hold our database connection pool
db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager to handle database connection pooling.
    Connects to PostgreSQL on startup and cleans up on shutdown.
    """
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "imdb_admin"),
            password=os.getenv("POSTGRES_PASSWORD", "supersecretpassword"),
            database=os.getenv("POSTGRES_DB", "imdb_ai_db"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", 5432),
        )
        yield
    finally:
        if db_pool:
            await db_pool.close()


# Initialize FastAPI app with Swagger UI documentation metadata
app = FastAPI(
    title="IMDB AI Pipeline API",
    description="API Gateway for accessing processed IMDB movie data.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/movies", summary="Get all movies", tags=["Movies"])
async def get_movies(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Retrieves a list of processed movies from the PostgreSQL database.
    """
    if not db_pool:
        raise HTTPException(
            status_code=500, detail="Database connection is not initialized."
        )

    query = """
        SELECT id, imdb_id, rank, title, rating, votes, status, updated_at 
        FROM movies 
        ORDER BY rank ASC 
        LIMIT $1 OFFSET $2;
    """

    async with db_pool.acquire() as connection:
        records = await connection.fetch(query, limit, offset)

    # Convert asyncpg.Record objects to standard Python dictionaries
    return [dict(record) for record in records]


@app.get("/movies/export", summary="Export movies to Excel", tags=["Export"])
async def export_movies_to_excel():
    """
    Generates an Excel (.xlsx) file on the fly containing all scraped movies.
    Perfect for business clients and data analysts.
    """
    if not db_pool:
        raise HTTPException(
            status_code=500, detail="Database connection is not initialized."
        )

    query = "SELECT rank, title, rating, votes, status FROM movies ORDER BY rank ASC;"

    async with db_pool.acquire() as connection:
        records = await connection.fetch(query)

    if not records:
        raise HTTPException(status_code=404, detail="No movies found in the database.")

    # 1. Convert database records to a Pandas DataFrame
    df = pd.DataFrame([dict(r) for r in records])

    # 2. Rename columns for a professional Excel look
    df.rename(
        columns={
            "rank": "Rank",
            "title": "Movie Title",
            "rating": "IMDB Rating",
            "votes": "Total Votes",
            "status": "AI Status",
        },
        inplace=True,
    )

    # 3. Write DataFrame to a virtual file (in-memory bytes buffer)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Top 250 Movies")

    # Reset buffer pointer to the beginning
    output.seek(0)

    # 4. Stream the file directly to the client's browser
    headers = {"Content-Disposition": 'attachment; filename="imdb_top_movies.xlsx"'}

    return StreamingResponse(
        output,
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
