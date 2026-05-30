# Compose build entrypoint for providers that do not honor build.dockerfile
# reliably on Windows. Service-specific Dockerfiles are kept in src/*.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS scraper

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY . .

RUN uv pip install src/contracts --system \
    && uv pip install -e src/scraper_python --system

RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["imdb-top250-scraper"]


FROM python:3.11-slim AS api

ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY src/api_fastapi/pyproject.toml ./
COPY src/api_fastapi/uv.lock ./

RUN uv sync --frozen --no-dev --no-editable

COPY src/api_fastapi/src ./src
COPY src/contracts ./src/contracts

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.11-slim AS worker_ai

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY src/worker_ai_python/pyproject.toml src/worker_ai_python/uv.lock ./

RUN uv sync --frozen

COPY ./src/worker_ai_python/src ./src
COPY ./src/contracts ./src/contracts

CMD ["uv", "run", "python", "src/main.py"]


FROM python:3.11-slim AS contract_tests

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY src/contracts /app/src/contracts/

RUN uv sync --project /app/src/contracts

CMD ["uv", "run", "--project", "src/contracts", "pytest", "src/contracts/test_contracts.py", "-v", "--tb=short"]
