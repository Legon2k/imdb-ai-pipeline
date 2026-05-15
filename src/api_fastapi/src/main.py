# --- START OF FILE main.py ---

import io
import os
import httpx
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

    query = "SELECT rank, title, rating, votes, status, ai_summary FROM movies ORDER BY rank ASC;"

    async with db_pool.acquire() as connection:
        records = await connection.fetch(query)

    if not records:
        raise HTTPException(status_code=404, detail="No movies found in the database.")

    # 1. Convert database records to a Pandas DataFrame
    df = pd.DataFrame([dict(r) for r in records])

    # 2. Rename columns for a professional Excel look
    df.rename(columns={
        "rank": "Rank",
        "title": "Movie Title",
        "rating": "IMDB Rating",
        "votes": "Total Votes",
        "status": "AI Status",
        "ai_summary": "AI Generated Summary"
    }, inplace=True)

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

@app.post("/movies/enrich", summary="Enrich pending movies using Local LLM", tags=["AI Enrichment"])
async def enrich_movies(limit: int = 5) -> Dict[str, Any]:
    """
    Fetches movies with status 'pending', sends them to a local LLM (Ollama/LM Studio) 
    to generate an engaging summary, and updates their status to 'completed'.
    """
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database connection is not initialized.")
    
    # 1. Fetch pending movies
    select_query = "SELECT id, title, rating FROM movies WHERE status = 'pending' LIMIT $1;"
    async with db_pool.acquire() as connection:
        pending_movies = await connection.fetch(select_query, limit)
    
    if not pending_movies:
        return {"message": "No pending movies found to enrich.", "processed": 0}

    llm_url = os.getenv("LLM_API_URL", "http://host.docker.internal:11434/api/generate")
    model_name = os.getenv("LLM_MODEL_NAME", "llama3")
    processed_count = 0
    results = []

    # 2. Setup Async HTTP Client for LLM communication
    async with httpx.AsyncClient(timeout=300.0) as client:
        for movie in pending_movies:
            movie_id = movie["id"]
            title = movie["title"]
            rating = movie["rating"]
            
            # Create a prompt for the LLM
            prompt = f"Write a short, engaging 1-sentence summary for the famous movie '{title}' (IMDB Rating: {rating}). Do not include any intro, just the summary."
            
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False
            }
            
            try:
                # 3. Call the Local LLM
                response = await client.post(llm_url, json=payload)
                response.raise_for_status()
                
                ai_data = response.json()
                summary = ai_data.get("response", "").strip() # Use "choices" if OpenAI/LM Studio format
                
                # 4. Update the database with the AI summary
                update_query = """
                    UPDATE movies 
                    SET ai_summary = $1, status = 'completed', updated_at = CURRENT_TIMESTAMP 
                    WHERE id = $2;
                """
                async with db_pool.acquire() as connection:
                    await connection.execute(update_query, summary, movie_id)
                
                results.append({"title": title, "summary": summary})
                processed_count += 1
                
            except Exception as e:
                # Log the error but continue processing the rest of the batch
                print(f"Error enriching movie '{title}': {repr(e)}")
                continue

    return {
        "message": f"Successfully enriched {processed_count} movies.",
        "details": results
    }