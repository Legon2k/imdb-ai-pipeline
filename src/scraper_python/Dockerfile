FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy package sources from the new src layout
COPY src/imdb_top.py ./imdb_top.py
COPY src/imdb_top250_scraper ./imdb_top250_scraper

RUN mkdir -p /data

ENTRYPOINT ["python", "imdb_top.py"]
CMD ["--output", "/data/imdb_top_250.json"]
