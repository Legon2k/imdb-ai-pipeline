FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY imdb_top.py .

RUN mkdir -p /data

ENTRYPOINT ["python", "imdb_top.py"]
CMD ["--output", "/data/imdb_top_250.json"]
