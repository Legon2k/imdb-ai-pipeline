# --- START OF FILE Dockerfile ---

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY ./src ./src

# Expose port 8000 for the FastAPI server
EXPOSE 8000

# Start Uvicorn server, pointing to the app instance in src.main
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]