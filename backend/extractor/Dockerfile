# syntax=docker/dockerfile:1

FROM python:3.14.7-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --no-log-init app \
    && chown -R app:app /app

USER app

EXPOSE 8001

CMD ["uvicorn", "extractor:app", "--host", "0.0.0.0", "--port", "8001"]
