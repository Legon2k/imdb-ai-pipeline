FROM python:3.11-slim

# Disable Python output buffering for real-time logging
ENV PYTHONUNBUFFERED=1

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy project configuration files to leverage Docker layer caching
COPY src/api_fastapi/pyproject.toml ./
COPY src/api_fastapi/uv.lock ./

# Install only production dependencies using uv
# Using --only-group to be explicit about excluding dev dependencies
RUN uv sync --frozen --no-dev --no-editable

# Copy the application source code
COPY src/api_fastapi/src ./src

# Copy contracts directory for import resolution
COPY src/contracts ./src/contracts

# Copy the VERSION file from the monorepo root to retrieve version at build-time
COPY VERSION ./

# Read VERSION and dynamically bake it as a static variable inside src/version.py
RUN echo "APP_VERSION = '$(cat VERSION)'" > src/version.py

# Expose port 8000 for the FastAPI server
EXPOSE 8000

# Start Uvicorn server using uv
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]