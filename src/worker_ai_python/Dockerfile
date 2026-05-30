FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY src/worker_ai_python/pyproject.toml src/worker_ai_python/uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen

# Copy source code and contracts
COPY ./src/worker_ai_python/src ./src
COPY ./src/contracts ./src/contracts

CMD ["uv", "run", "python", "src/main.py"]
