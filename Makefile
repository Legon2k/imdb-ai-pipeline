.PHONY: install install-dev install-browser test test-contracts test-all lint format scrape docker-build docker-run compose-run

SHELL := pwsh.exe
.SHELLFLAGS := -NoProfile -Command

install:
	uv sync --project src/scraper_python
	uv sync --project src/worker_ai_python

install-dev:
	uv sync --project src/scraper_python

install-browser:
	python -m playwright install chromium

install-test:
	uv pip install -r requirements-test.txt

test:
	uv run --project src/scraper_python python -B -m unittest discover -s src/scraper_python/tests -t src/scraper_python
	uv run --project src/scraper_python python -B -m unittest discover -s src/api_fastapi/tests

test-contracts:
	uv run --project src/scraper_python python -m pytest contracts/test_contracts.py -v --tb=short

test-all: test test-contracts

test-docker:
	docker compose --profile test up contract-tests

lint:
	$$env:VIRTUAL_ENV = $$null; uv run --project src/scraper_python ruff check .
	$$env:VIRTUAL_ENV = $$null; uv run --project src/worker_ai_python ruff check .

format:
	$$env:VIRTUAL_ENV = $$null; uv run --project src/scraper_python ruff format .
	$$env:VIRTUAL_ENV = $$null; uv run --project src/worker_ai_python ruff format .

scrape:
	uv run --project src/scraper_python python -B src/scraper_python/src/imdb_top.py

docker-build:
	docker build -t imdb-top250-scraper src/scraper_python

docker-run:
	docker run --rm -v "$(CURDIR)/data:/data" imdb-top250-scraper

compose-run:
	docker compose run --rm scraper
