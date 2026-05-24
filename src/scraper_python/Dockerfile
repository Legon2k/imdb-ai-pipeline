# Use the official Playwright Python image as the base
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

# Copy the uv binary directly from the official image (multi-stage build)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory to the /app
WORKDIR /app

# Copy the entire project to the container
COPY . .

# Install the contracts package globally
RUN uv pip install src/contracts --system

# Install the scraper package globally in editable mode
RUN uv pip install -e src/scraper_python --system

# Set the execution entry point using the installed console script
ENTRYPOINT ["imdb-top250-scraper"]