# Use a lightweight Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set the working directory inside the container
WORKDIR /app

# Optimize Python and uv behavior for Docker containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy the entire project to the container
COPY . .

# Read the root VERSION file and bake it statically into the package before installation
RUN echo "APP_VERSION = '$(cat VERSION)'" > src/scraper_python/imdb_top250_scraper/version.py

# Install the local contracts package globally in the system
RUN uv pip install src/contracts --system \
    # Install the scraper package globally in editable mode
    && uv pip install -e src/scraper_python --system

# Download ONLY Chromium and its specific Linux dependencies
# Keep this compatible with classic Docker builders and Podman providers
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Set the execution entry point using your installed console script
ENTRYPOINT ["imdb-top250-scraper"]