.PHONY: install install-dev install-browser test test-contracts test-all lint format scrape docker-build docker-run compose-run

install:
	python -m pip install -r src/scraper_python/requirements.txt

install-dev:
	python -m pip install -r src/scraper_python/requirements-dev.txt

install-browser:
	python -m playwright install chromium

install-test:
	python -m pip install -r requirements-test.txt

test:
	python -B -m unittest discover -s src/scraper_python/tests
	python -B -m unittest discover -s src/api_fastapi/tests

test-contracts:
	python -m pytest contracts/test_contracts.py -v --tb=short

test-all: test test-contracts

test-docker:
	docker compose --profile test up contract-tests

lint:
	ruff check .

format:
	ruff format .

scrape:
	python -B src/scraper_python/src/imdb_top.py

docker-build:
	docker build -t imdb-top250-scraper src/scraper_python

docker-run:
	docker run --rm -v "$(CURDIR)/data:/data" imdb-top250-scraper

compose-run:
	docker compose run --rm scraper
