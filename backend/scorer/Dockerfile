# syntax=docker/dockerfile:1

FROM python:3.14.7-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --no-log-init app \
    && chown -R app:app /app

USER app

EXPOSE 8002

CMD ["uvicorn", "scorer:app", "--host", "0.0.0.0", "--port", "8002"]
