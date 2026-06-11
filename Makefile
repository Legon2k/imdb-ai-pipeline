.PHONY: install install-dev install-browser install-test test test-contracts test-all test-docker lint format scrape docker-build docker-run compose-config compose-build compose-up compose-ps compose-run

CONTAINER_ENGINE ?= docker
COMPOSE ?= $(CONTAINER_ENGINE) compose

ifeq ($(OS),Windows_NT)
    SHELL := pwsh.exe
    .SHELLFLAGS := -NoProfile -Command
else
    # Настройки для Linux / macOS
    SHELL := /bin/bash
    .SHELLFLAGS := -c
endif

install:
	uv sync --project src/scraper_python
	uv sync --project src/worker_ai_python
	uv sync --project src/api_fastapi

install-dev:
	uv sync --project src/scraper_python

install-browser:
	python -m playwright install chromium

install-test:
	$$env:VIRTUAL_ENV = $$null; uv sync --project src/contracts

test:
	uv run --project src/scraper_python python -B -m unittest discover -s src/scraper_python/tests -t src/scraper_python
	uv run --project src/scraper_python python -B -m unittest discover -s src/api_fastapi/tests

test-contracts:
	$$env:VIRTUAL_ENV = $$null; uv run --project src/contracts pytest src/contracts/test_contracts.py -v --tb=short

test-all: test test-contracts

test-docker:
	$(COMPOSE) --profile test up contract-tests

lint:
	$$env:VIRTUAL_ENV = $$null; uv run --project src/scraper_python ruff check .
	$$env:VIRTUAL_ENV = $$null; uv run --project src/worker_ai_python ruff check .
	$$env:VIRTUAL_ENV = $$null; uv run --project src/api_fastapi ruff check .

format:
	$$env:VIRTUAL_ENV = $$null; uv run --project src/scraper_python ruff format .
	$$env:VIRTUAL_ENV = $$null; uv run --project src/worker_ai_python ruff format .
	$$env:VIRTUAL_ENV = $$null; uv run --project src/api_fastapi ruff format .

scrape:
	uv run --project src/scraper_python python -B src/scraper_python/src/imdb_top.py

docker-build:
	$(CONTAINER_ENGINE) build -t imdb-top250-scraper src/scraper_python

docker-run:
	$(CONTAINER_ENGINE) run --rm -v "$(CURDIR)/data:/data" imdb-top250-scraper

compose-config:
	$(COMPOSE) config

compose-build:
	$(COMPOSE) build

compose-up:
	$(COMPOSE) up -d

compose-ps:
	$(COMPOSE) ps

compose-run:
	$(COMPOSE) run --rm scraper

# Run performance bench setup (populates Redis Stream with 5M items)
# Default count if not specified externally
count ?= 1000

load-bench-fill:
	@echo "Populating Redis stream with $(count) messages..."
	uv run --isolated --with redis --with python-dotenv --env-file .env tests/load_bench/fill_redis_stream.py --host 127.0.0.1 --count $(count)

load-bench-clean:
	@echo "Cleaning Redis stream..."
	podman exec -it imdb_redis redis-cli XTRIM movies_stream MAXLEN 100	