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
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_HTTP_TIMEOUT=120

# Copy workspace metadata first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./
COPY src/contracts/pyproject.toml ./src/contracts/
COPY src/scraper_python/pyproject.toml ./src/scraper_python/

# Build dependencies with BuildKit cache mounts for rapid rebuilds
RUN --mount=type=cache,target=/root/.cache/uv \
    mkdir -p src/contracts/src src/scraper_python/src && \
    touch src/contracts/src/__init__.py src/scraper_python/src/__init__.py && \
    uv pip install --system ./src/contracts ./src/scraper_python

# Install Playwright browsers and their OS-level system dependencies
RUN playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# Copy actual source code
COPY src/contracts /app/src/contracts
COPY src/scraper_python /app/src/scraper_python

# Finalize package installation in editable mode for local runs
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -e src/contracts --system && \
    uv pip install -e src/scraper_python --system

ENTRYPOINT ["imdb-top250-scraper"]


# ==============================================================================
# STAGE 2: API Service (FastAPI)
# ==============================================================================
FROM python:3.12-slim AS api

ENV PYTHONUNBUFFERED=1

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace metadata files
COPY pyproject.toml uv.lock ./
COPY src/api_fastapi/pyproject.toml ./src/api_fastapi/
COPY src/contracts/pyproject.toml ./src/contracts/

# Step 1: Install third-party dependencies only
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project src/api_fastapi --frozen --no-dev --no-install-project

# Copy actual application source code and contracts
COPY src/api_fastapi/src ./src/api_fastapi/src
COPY src/contracts /app/src/contracts

# Step 2: Link workspace members in editable mode (fixes ModuleNotFoundError)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project src/api_fastapi --frozen --no-dev --editable

# Inject virtual environment binaries directly into the system PATH
ENV PATH="/app/.venv/bin:$PATH"

# Configure robust PYTHONPATH supporting both flat and src package layouts
ENV PYTHONPATH="/app:/app/src:/app/src/contracts:/app/src/contracts/src"

# Expose API port
EXPOSE 8000

# Fix file permissions for nobody user (Debian uses nogroup)
RUN chown -R nobody:nogroup /app

# Switch to non-privileged user for security compliance
USER nobody

CMD ["uvicorn", "src.api_fastapi.src.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ==============================================================================
# STAGE 3: Worker AI Service
# ==============================================================================
FROM python:3.12-slim AS worker_ai

ENV PYTHONUNBUFFERED=1

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace metadata files
COPY pyproject.toml uv.lock ./
COPY src/worker_ai_python/pyproject.toml ./src/worker_ai_python/
COPY src/contracts/pyproject.toml ./src/contracts/

# Step 1: Install third-party dependencies only
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project src/worker_ai_python --frozen --no-dev --no-install-project

# Copy actual application source code and contracts
COPY ./src/worker_ai_python/src ./src
COPY ./src/contracts ./src/contracts

# Step 2: Link workspace members in editable mode
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project src/worker_ai_python --frozen --no-dev --editable

# Inject virtual environment binaries into the system PATH
ENV PATH="/app/.venv/bin:$PATH"

# Configure robust PYTHONPATH supporting both flat and src package layouts
ENV PYTHONPATH="/app:/app/src:/app/src/contracts:/app/src/contracts/src"

# Fix file permissions for nobody user (Debian uses nogroup)
RUN chown -R nobody:nogroup /app

# Switch to non-privileged user for security compliance
USER nobody

CMD ["python", "src/main.py"]


# ==============================================================================
# STAGE 4: Contract Tests
# ==============================================================================
FROM python:3.12-slim AS contract_tests

WORKDIR /app

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the contracts package metadata
COPY pyproject.toml uv.lock ./
COPY src/contracts/pyproject.toml /app/src/contracts/

# Step 1: Install third-party test dependencies first
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project src/contracts --frozen --no-install-project

# Copy the remaining test files and implementation
COPY src/contracts /app/src/contracts/

# Step 2: Finalize test environment setup in editable mode
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project src/contracts --frozen --editable

# Inject virtual environment binaries into system PATH
ENV PATH="/app/.venv/bin:$PATH"

CMD ["pytest", "src/contracts/test_contracts.py", "-v", "--tb=short"]