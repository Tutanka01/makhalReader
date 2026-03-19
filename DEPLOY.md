# Deploying MakhalReader to Production

A complete guide to expose MakhalReader on the internet with TLS, authentication, and proper security.

---

## Prerequisites

- A Linux VPS (Ubuntu 22.04+ recommended, 1 GB RAM minimum)
- A domain name pointing to your server's IP (A record)
- Docker + Docker Compose installed (`curl -fsSL https://get.docker.com | sh`)
- Ports 80 and 443 open in your firewall

---

## 1. Clone & configure

```bash
git clone <your-repo-url> makhalreader
cd makhalreader
```

Copy the example env file and fill in every value:

```bash
cp .env.example .env
nano .env
```

### Required variables

| Variable | Example | Notes |
|---|---|---|
| `AUTH_PASSWORD` | `openssl rand -base64 32` | **Never reuse passwords.** Store it somewhere safe. |
| `CADDY_DOMAIN` | `reader.yourdomain.com` | Must match your DNS A record. |
| `CORS_ORIGIN` | `https://reader.yourdomain.com` | Exact origin, no trailing slash. |
| `API_SECRET` | `openssl rand -hex 32` | Internal service-to-service secret. |
| `OPENROUTER_API_KEY` | `sk-or-...` | For AI scoring via OpenRouter. |
| `HTTPS_ONLY` | `true` | **Leave as `true` in production.** |

### Optional tuning

```env
MAX_NEW_ARTICLES_PER_FEED=5      # Articles ingested per feed per poll
MAX_ARTICLE_AGE_DAYS=7           # Skip articles older than N days
SCORE_DELAY_SECONDS=2.0          # Delay between LLM calls (rate limiting)
MAX_ARTICLES_PER_FEED=200        # Max articles kept per feed
ARTICLE_RETENTION_DAYS=90        # Delete articles older than N days
```

---

## 2. Delete the local override file

The `docker-compose.override.yml` is for local development only. In production it **must not** be present:

```bash
rm docker-compose.override.yml
```

> **Why:** The override enables HTTP on port 80 with a local Caddyfile that has no TLS and no security headers. Without removing it, Caddy will use the wrong config.

---

## 3. Verify your `.env`

Your production `.env` should look like:

```env
# LLM
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
SCORER_MODEL=google/gemini-flash-1.5

# App
FETCH_INTERVAL_MINUTES=15
DB_PATH=/data/makhal.db
API_SECRET=<64-char hex string>

# Auth
AUTH_PASSWORD=<strong random password>
HTTPS_ONLY=true
CORS_ORIGIN=https://reader.yourdomain.com

# Caddy
CADDY_DOMAIN=reader.yourdomain.com

# Guardrails
MAX_NEW_ARTICLES_PER_FEED=5
MAX_ARTICLE_AGE_DAYS=7
SCORE_DELAY_SECONDS=2.0
MAX_ARTICLES_PER_FEED=200
ARTICLE_RETENTION_DAYS=90
```

**Never commit `.env` to git.** Verify `.gitignore` includes it:

```bash
grep '.env' .gitignore || echo '.env' >> .gitignore
```

---

## 4. Launch

```bash
docker compose up -d --build
```

Caddy will automatically obtain a Let's Encrypt TLS certificate on first startup. Wait ~30 seconds, then open `https://reader.yourdomain.com` in your browser. You should see the login page.

---

## 5. Verify everything is working

```bash
# All containers should be "Up"
docker compose ps

# Check API health
curl https://reader.yourdomain.com/api/health

# Check auth endpoint (should return 401)
curl https://reader.yourdomain.com/auth/status

# Tail logs
docker compose logs -f --tail=50
```

---

## 6. Firewall (UFW)

```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (Caddy redirects to HTTPS)
ufw allow 443/tcp   # HTTPS
ufw enable
```

Internal services (API :8000, extractor :8001, scorer :8002) are **not** exposed to the internet — they are only accessible within the Docker network. Do not add UFW rules for them.

---

## Updating

```bash
git pull
docker compose build
docker compose up -d
```

Zero-downtime: Docker Compose restarts containers one by one. The database volume (`data`) persists across updates.

---

## Backup

The entire state is in one SQLite file:

```bash
# Backup
docker compose exec api sqlite3 /data/makhal.db ".backup /data/makhal.db.bak"
docker compose cp api:/data/makhal.db.bak ./makhal.db.bak

# Restore
docker compose cp ./makhal.db.bak api:/data/makhal.db
docker compose restart api
```

---

## Changing the password

Edit `.env`, change `AUTH_PASSWORD`, then restart the API:

```bash
docker compose up -d api
```

Existing sessions remain valid until they expire (24h short / 1 year "remember me"). To invalidate all sessions immediately, delete the `auth_sessions` table:

```bash
docker compose exec api sqlite3 /data/makhal.db "DELETE FROM auth_sessions;"
```

---

## Security checklist

- [ ] `AUTH_PASSWORD` is a strong random string (≥ 32 chars)
- [ ] `API_SECRET` is a strong random string (≥ 32 chars)
- [ ] `HTTPS_ONLY=true`
- [ ] `CORS_ORIGIN` matches your exact domain
- [ ] `docker-compose.override.yml` is deleted
- [ ] `.env` is not committed to git
- [ ] Ports 8000, 8001, 8002 are NOT exposed in UFW
- [ ] TLS certificate is valid (`curl -I https://reader.yourdomain.com`)
- [ ] Login page appears at your domain

---

## Troubleshooting

**Login page doesn't appear / all requests return 401**
- Make sure `docker-compose.override.yml` is deleted
- Verify Caddy is routing `/auth/*` to the API: `docker compose logs caddy`

**TLS certificate not issued**
- Verify your DNS A record points to the server IP
- Port 80 must be reachable (Let's Encrypt HTTP challenge)
- Check: `docker compose logs caddy`

**Password rejected**
- `AUTH_PASSWORD` in `.env` must not have shell-escaping issues
- If it contains `$` or `!`, wrap it in single quotes in `.env`:
  `AUTH_PASSWORD='my$ecret!'`
- Restart after any `.env` change: `docker compose up -d api`

**Scorer not working**
- Check `OPENROUTER_API_KEY` is valid
- Check scorer logs: `docker compose logs scorer`
