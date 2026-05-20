# Use the official Playwright Python image as the base
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

# Copy the uv binary directly from the official image (multi-stage build)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency definition files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies globally inside the container using uv
# --system forces uv to install packages into the system Python environment
RUN uv sync --frozen --no-dev

# Copy the rest of the application source code
COPY . .

# Set the execution entry point inside the scraper folder structure
ENTRYPOINT ["uv", "run", "python", "src/imdb_top250_scraper/cli.py"]