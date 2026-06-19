# ==============================================================================
# STAGE 1: Scraper Service
# ==============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS scraper

WORKDIR /app

# Optimize Python and uv behavior for Docker containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# --- STEP 1: Copy workspace configuration files to satisfy uv workspace checks ---
# We copy pyproject.toml from the root and config files of required packages
COPY pyproject.toml uv.lock* ./
COPY src/contracts/pyproject.toml ./src/contracts/
COPY src/scraper_python/pyproject.toml ./src/scraper_python/

# --- STEP 2: Copy the actual source code to allow workspace building ---
COPY src/contracts /app/src/contracts
COPY src/scraper_python /app/src/scraper_python

# --- STEP 3: Install packages globally within the system ---
# Now uv sees the full workspace context and links everything without errors
RUN uv pip install --system ./src/contracts ./src/scraper_python

# --- STEP 4: Install system dependencies and Chromium (Heavily Cached) ---
# This layer remains frozen in the cache and won't re-download on code changes
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# --- STEP 5: Finalize package linking in editable mode ---
RUN uv pip install -e src/contracts --system \
    && uv pip install -e src/scraper_python --system

ENTRYPOINT ["imdb-top250-scraper"]


# ==============================================================================
# STAGE 2: API Service (FastAPI)
# ==============================================================================
FROM python:3.11-slim AS api

# Disable Python output buffering for real-time logging
ENV PYTHONUNBUFFERED=1

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace configuration files to let uv resolve global dependencies
COPY pyproject.toml uv.lock* ./
COPY src/api_fastapi/pyproject.toml ./src/api_fastapi/
COPY src/contracts/pyproject.toml ./src/contracts/

# Sync dependencies specifically for the api project using workspace context
RUN uv sync --project src/api_fastapi --frozen --no-dev --no-editable

# Copy the actual application source code and contracts
COPY src/api_fastapi/src ./src/api_fastapi/src
COPY src/contracts /app/src/contracts

# FIXED: Configure PYTHONPATH to allow resolution of local workspace packages
ENV PYTHONPATH="/app:/app/src:/app/src/contracts"

# Expose port 8000 for the FastAPI server
EXPOSE 8000

# Run uvicorn pointing to the exact package location
CMD ["/app/.venv/bin/uvicorn", "src.api_fastapi.src.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ==============================================================================
# STAGE 3: Worker AI Service
# ==============================================================================
FROM python:3.11-slim AS worker_ai

# Disable Python output buffering for real-time logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project configuration files to leverage Docker layer caching
COPY src/worker_ai_python/pyproject.toml src/worker_ai_python/uv.lock ./

# Install project dependencies into the virtual environment during build stage
RUN uv sync --frozen

# Copy the application source code and local dependencies
COPY ./src/worker_ai_python/src ./src
COPY ./src/contracts ./src/contracts

# Add the virtual environment binaries to PATH to avoid "uv run" overhead at runtime
ENV PATH="/app/.venv/bin:$PATH"

# Execute the python script directly from the active virtual environment
CMD ["python", "src/main.py"]


# ==============================================================================
# STAGE 4: Contract Tests
# ==============================================================================
FROM python:3.11-slim AS contract_tests

WORKDIR /app

# Copy the uv binary from the official image for consistency and speed
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy the contracts package metadata first for better caching
COPY src/contracts/pyproject.toml /app/src/contracts/

# Run uv sync during the build phase to prepare the testing environment
RUN uv sync --project /app/src/contracts

# Copy the remaining test files and implementation
COPY src/contracts /app/src/contracts/

# Add test environment virtual binaries to PATH
ENV PATH="/app/src/contracts/.venv/bin:$PATH"

# Run pytest directly from the environment without "uv run" wrapping
CMD ["pytest", "src/contracts/test_contracts.py", "-v", "--tb=short"]