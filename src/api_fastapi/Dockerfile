# Use a lightweight Python image with uv pre-installed
FROM python:3.11-slim

# Disable Python output buffering for real-time logging
ENV PYTHONUNBUFFERED=1

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy project configuration files to leverage Docker layer caching
COPY src/api_fastapi/pyproject.toml ./
COPY src/api_fastapi/uv.lock ./

# Install only production dependencies using uv during the build stage
RUN uv sync --frozen --no-dev --no-editable

# Copy the application source code and local dependencies
COPY src/api_fastapi/src ./src
COPY src/contracts ./src/contracts

# Add the virtual environment binaries to PATH so we don't need "uv run" at runtime
ENV PATH="/app/.venv/bin:$PATH"

# Expose port 8000 for the FastAPI server
EXPOSE 8000

# Start Uvicorn directly from the virtual environment for maximum performance
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]