# syntax=docker/dockerfile:1

# Debian bookworm is pinned explicitly: the floating -slim tag now resolves to trixie.
FROM python:3.12.14-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user. The entrypoint starts as root only to fix the
# ownership of an existing /data volume, then drops privileges with setpriv
# (shipped with util-linux in Debian slim, so no extra package is needed).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --no-log-init app \
    && mkdir -p /data \
    && chown -R app:app /app /data \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
