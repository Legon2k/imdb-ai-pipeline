# Use a lightweight Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set the working directory inside the container
WORKDIR /app

# Optimize Python and uv behavior for Docker containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# --- STEP 1: Prepare directory structure for caching ---
# Create empty package directories so uv can parse local paths correctly
RUN mkdir -p src/contracts src/scraper_python

# Copy ONLY package configuration files to leverage Docker layer caching
# This ensures dependencies are not re-downloaded unless configs change
COPY src/contracts/pyproject.toml src/contracts/
COPY src/scraper_python/pyproject.toml src/scraper_python/

# --- STEP 2: Install external dependencies ---
# Install third-party packages from PyPI before copying the actual source code
RUN uv pip install --system ./src/contracts ./src/scraper_python

# --- STEP 3: Install system dependencies and Chromium ---
# Download Chromium and its required Linux libraries (.so files)
# This layer is heavily cached and won't re-run when you change your python code
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# --- STEP 4: Copy source code and link packages ---
# Copy the actual source code into the container (runs in milliseconds)
COPY src/contracts/src src/contracts/src
COPY src/scraper_python/src src/scraper_python/src

# Re-install local packages in editable mode to link the copied source code globally
RUN uv pip install -e src/contracts --system \
    && uv pip install -e src/scraper_python --system

# Set the execution entry point using the installed console script
ENTRYPOINT ["imdb-top250-scraper"]