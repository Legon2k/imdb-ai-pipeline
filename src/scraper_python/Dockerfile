# Use the official Playwright Python image as the base
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

# Copy the uv binary directly from the official image (multi-stage build)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency definition files first to leverage Docker layer caching
COPY src/scraper_python/pyproject.toml src/scraper_python/uv.lock ./

# Copy the contracts package to /contracts so relative path resolution works
COPY src/contracts /contracts

# Install project dependencies globally inside the container using uv
# --system forces uv to install packages into the system Python environment
RUN uv sync --frozen --no-dev

# Copy the rest of the scraper application source code
COPY src/scraper_python . 

# Update pyproject.toml to use absolute path for Docker, then install
RUN sed -i 's|file://../contracts|file:///contracts|g' pyproject.toml && \
    cd /app && uv pip install -e . --system

# Set the execution entry point using the installed console script
ENTRYPOINT ["imdb-top250-scraper"]