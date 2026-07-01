# Deploying MakhalReader

MakhalReader supports two Compose modes:

- **Local standalone mode**: Docker publishes the app on `http://localhost`.
- **Production behind Nginx Proxy Manager**: NPM owns ports `80/443`; MakhalReader only joins NPM's Docker network.

The difference matters. The frontend calls the API with relative browser paths such as `/api/articles` and `/auth/login`. If NPM points directly to the `frontend` container, those paths are handled by the frontend Nginx container instead of FastAPI, so the UI loads but login, feeds, and articles do not work.

MakhalReader therefore includes a small internal `web` proxy:

```text
browser
  -> local port 80 OR Nginx Proxy Manager
  -> makhal-reader-web:80
      /api/*  -> api:8000
      /auth/* -> api:8000
      /*      -> frontend:80
```

---

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base services and private app network. No public host ports. |
| `docker-compose.override.yml` | Local-only override, loaded automatically by `docker compose up`; publishes `web` on `80:80`. |
| `docker-compose.npm.yml` | Production NPM override; attaches `web` to external network `npm_default`. |
| `nginx/npm.conf` | Internal routing from `web` to `api` and `frontend`. |

---

## Local Development

Use this when there is no Nginx Proxy Manager network on the machine.

```bash
cp .env.example .env
# For local HTTP:
# HTTPS_ONLY=false
# CORS_ORIGIN=

docker compose up -d --build
```

Open:

```text
http://localhost
```

Why this works locally:

- `docker-compose.override.yml` is loaded automatically by Docker Compose.
- It publishes `makhal-reader-web` on host port `80`.
- It does not require the external `npm_default` network.
- The API still stays internal; browser calls go through `web` via `/api/*` and `/auth/*`.

---

## Production With Nginx Proxy Manager

Prerequisites:

- Nginx Proxy Manager is already running.
- NPM has a Docker network named `npm_default`.
- Your domain points to the server running NPM.
- NPM owns host ports `80` and `443`.

Configure `.env`:

```env
HTTPS_ONLY=true
CORS_ORIGIN=https://reader.yourdomain.com
AUTH_PASSWORD=<strong random string>
API_SECRET=<strong random string>
```

Launch without the local override and with the NPM override:

```bash
docker compose -f docker-compose.yml -f docker-compose.npm.yml up -d --build
```

Configure the NPM Proxy Host:

```text
Domain Names: reader.yourdomain.com
Scheme: http
Forward Hostname / IP: makhal-reader-web
Forward Port: 80
Websockets Support: enabled
SSL: request/attach certificate, Force SSL enabled
```

Do not point NPM to `frontend` directly. It must point to `makhal-reader-web`, otherwise `/api/*` and `/auth/*` will not reach FastAPI.

---

## Verify

Local:

```bash
curl http://localhost/api/health
curl -i http://localhost/auth/status
```

Production:

```bash
curl https://reader.yourdomain.com/api/health
curl -i https://reader.yourdomain.com/auth/status
```

Expected:

- `/api/health` returns OK.
- `/auth/status` returns `401` before login.
- After login in the browser, articles and feeds load normally.

Check services:

```bash
docker compose ps
docker compose logs -f --tail=50 web api frontend
```

For production commands, include the NPM file:

```bash
docker compose -f docker-compose.yml -f docker-compose.npm.yml ps
docker compose -f docker-compose.yml -f docker-compose.npm.yml logs -f --tail=50 web api frontend
```

---

## Updating

Local:

```bash
git pull
docker compose up -d --build
```

Production:

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.npm.yml up -d --build
```

The `data` volume survives rebuilds.

---

## Backup & Restore

All state lives in SQLite under the Docker volume mounted at `/data`.

```bash
# Backup
docker compose exec api python -c "import sqlite3; src=sqlite3.connect('/data/makhal.db'); dst=sqlite3.connect('/data/makhal.db.bak'); src.backup(dst); dst.close(); src.close()"
docker compose cp api:/data/makhal.db.bak ./makhal.db.bak

# Restore
docker compose cp ./makhal.db.bak api:/data/makhal.db
docker compose restart api
```

The `api` image is based on `python:3.12-slim`; use Python's `sqlite3` module
unless the image is explicitly changed to install the `sqlite3` CLI.

For production, use the same commands with `-f docker-compose.yml -f docker-compose.npm.yml`.

---

## Changing The Password

Edit `AUTH_PASSWORD` in `.env`, then restart the API:

```bash
docker compose up -d api
```

To invalidate all active sessions:

```bash
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); db.execute('DELETE FROM auth_sessions'); db.commit(); db.close()"
```

---

## Security Checklist

- [ ] `AUTH_PASSWORD` is a strong random string.
- [ ] `API_SECRET` is a strong random string.
- [ ] Production uses `HTTPS_ONLY=true`.
- [ ] Production `CORS_ORIGIN` exactly matches the public origin, with no trailing slash.
- [ ] NPM forwards to `makhal-reader-web:80`, not to `frontend`.
- [ ] Host ports `8000`, `8001`, and `8002` are not exposed publicly.
- [ ] `.env` is not committed to git.

---

## Troubleshooting

**Frontend loads but login/articles/feeds do not work**

- NPM is probably forwarding to `frontend` instead of `makhal-reader-web`.
- Confirm the NPM target is `makhal-reader-web` port `80`.
- Check routing through the internal proxy:

```bash
docker compose -f docker-compose.yml -f docker-compose.npm.yml logs web api --tail=100
```

**Production fails with `network npm_default not found`**

- NPM's Docker network has a different name.
- Check it:

```bash
docker network ls
```

- Either rename the network in `docker-compose.npm.yml`, or attach NPM and MakhalReader to the same external network.

**Login succeeds locally but not in production**

- Ensure the browser uses HTTPS.
- Set `HTTPS_ONLY=true`.
- Set `CORS_ORIGIN=https://reader.yourdomain.com`.
- In NPM, enable Force SSL.

**Articles are not being scored**

- Verify `OPENROUTER_API_KEY` is valid, or that `OLLAMA_URL` is reachable.
- Check:

```bash
docker compose logs scorer --tail=50
```
