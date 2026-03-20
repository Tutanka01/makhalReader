# Deploying MakhalReader

Everything you need to go from zero to a production-grade, TLS-secured, authenticated instance.

---

## Prerequisites

- A Linux VPS (Ubuntu 22.04+, 1 GB RAM minimum)
- A domain pointing to your server's IP (`A` record)
- Docker + Docker Compose (`curl -fsSL https://get.docker.com | sh`)
- Ports 80 and 443 open in your firewall

---

## 1. Clone & configure

```bash
git clone <your-repo-url> makhalreader
cd makhalreader

cp .env.example .env
nano .env
```

### Variables that matter

| Variable | Notes |
|----------|-------|
| `AUTH_PASSWORD` | Your login password — generate with `openssl rand -base64 32`. Never reuse. |
| `CADDY_DOMAIN` | Your domain, e.g. `reader.yourdomain.com`. Must match your DNS A record. |
| `CORS_ORIGIN` | Same domain, full URL, no trailing slash: `https://reader.yourdomain.com` |
| `API_SECRET` | Internal service secret — `openssl rand -hex 32`. Never expose publicly. |
| `OPENROUTER_API_KEY` | LLM scoring via OpenRouter. Leave blank to use Ollama locally. |
| `HTTPS_ONLY` | Keep `true` in production. Enforces secure cookies. |

### Tuning (optional)

```env
MAX_NEW_ARTICLES_PER_FEED=5      # Articles ingested per feed per poll
MAX_ARTICLE_AGE_DAYS=7           # Drop articles older than N days
SCORE_DELAY_SECONDS=2.0          # Pause between LLM calls (rate limiting)
MAX_ARTICLES_PER_FEED=200        # Articles retained per feed
ARTICLE_RETENTION_DAYS=90        # Hard-delete after N days (0 = off)
```

### What a clean production `.env` looks like

```env
# LLM
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
SCORER_MODEL=google/gemini-flash-1.5

# App
FETCH_INTERVAL_MINUTES=15
DB_PATH=/data/makhal.db
API_SECRET=<64-char hex>

# Auth
AUTH_PASSWORD=<strong random string>
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

> **Never commit `.env` to git.** Double-check: `grep '.env' .gitignore`

---

## 2. Drop the local override

`docker-compose.override.yml` is for local development only — it rewrites Caddy's config
to use plain HTTP and disables security headers.
In production it must not exist:

```bash
rm docker-compose.override.yml
```

---

## 3. Launch

```bash
docker compose up -d --build
```

Caddy provisions a Let's Encrypt certificate on first boot.
Give it ~30 seconds, then open `https://reader.yourdomain.com` — you should see the login page.

---

## 4. Verify

```bash
# All 6 containers should report "Up"
docker compose ps

# Health check
curl https://reader.yourdomain.com/api/health

# Should return 401 (auth is working)
curl https://reader.yourdomain.com/auth/status

# Live logs across all services
docker compose logs -f --tail=50
```

---

## Firewall (UFW)

```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP — Caddy redirects to HTTPS
ufw allow 443/tcp   # HTTPS
ufw enable
```

Internal ports (API :8000, extractor :8001, scorer :8002) are Docker-network-only.
Do **not** expose them via UFW.

---

## Updating

```bash
git pull
docker compose build
docker compose up -d
```

The database volume (`data`) survives rebuilds — no data loss.

---

## Backup & restore

All state lives in a single SQLite file.

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

Edit `AUTH_PASSWORD` in `.env`, then:

```bash
docker compose up -d api
```

Sessions are valid for 24h (or 1 year with "remember me").
To invalidate all active sessions immediately:

```bash
docker compose exec api sqlite3 /data/makhal.db "DELETE FROM auth_sessions;"
```

---

## Security checklist

- [ ] `AUTH_PASSWORD` is a random string ≥ 32 characters
- [ ] `API_SECRET` is a random string ≥ 32 characters
- [ ] `HTTPS_ONLY=true`
- [ ] `CORS_ORIGIN` matches your exact domain
- [ ] `docker-compose.override.yml` is deleted
- [ ] `.env` is not committed to git
- [ ] Ports 8000, 8001, 8002 are **not** in UFW rules
- [ ] `curl -I https://reader.yourdomain.com` returns `200` with a valid cert

---

## Troubleshooting

**Login page missing / 401 on everything**
- Confirm `docker-compose.override.yml` is deleted
- Check Caddy is routing `/auth/*` correctly: `docker compose logs caddy`

**TLS certificate not issued**
- Verify your DNS A record resolves to this server's IP
- Port 80 must be reachable (Let's Encrypt HTTP-01 challenge)
- Check: `docker compose logs caddy`

**Password rejected**
- If `AUTH_PASSWORD` contains `$` or `!`, wrap it in single quotes in `.env`:
  `AUTH_PASSWORD='my$tr0ng!pass'`
- Always restart after changing `.env`: `docker compose up -d api`

**Articles not being scored**
- Verify `OPENROUTER_API_KEY` is valid (or `OLLAMA_URL` is reachable)
- Check: `docker compose logs scorer --tail=50`
