.PHONY: install install-dev install-browser test lint format scrape docker-build docker-run compose-run

install:
	python -m pip install -r src/scraper_python/requirements.txt

install-dev:
	python -m pip install -r src/scraper_python/requirements-dev.txt

install-browser:
	python -m playwright install chromium

test:
	python -B -m unittest discover -s src/scraper_python/tests

lint:
	ruff check .

format:
	ruff format .

scrape:
	python -B imdb_top.py

docker-build:
	docker build -t imdb-top250-scraper .

docker-run:
	docker run --rm -v "$(CURDIR)/data:/data" imdb-top250-scraper

compose-run:
	docker compose run --rm scraper
