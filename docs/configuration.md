# Configuration

La configuration se fait par `.env`, charge par Docker Compose pour les services backend.

## Variables critiques

| Variable | Service | Description |
| --- | --- | --- |
| `AUTH_PASSWORD` | `api` | Mot de passe utilisateur. Obligatoire. |
| `API_SECRET` | `api`, `poller`, `scorer` | Secret entre services pour `/api/internal/*`. |
| `DB_PATH` | `api` | Chemin SQLite. Defaut attendu : `/data/makhal.db`. |
| `HTTPS_ONLY` | `api` | Cookie secure si `true`. Mettre `false` seulement en HTTP local. |
| `CORS_ORIGIN` | `api` | Origine publique exacte en production. |

En production, `AUTH_PASSWORD` et `API_SECRET` doivent etre generes comme secrets forts. Ne pas conserver les valeurs `change_me...` ou `changeme`.

## LLM

| Variable | Description |
| --- | --- |
| `OPENROUTER_API_KEY` | Active OpenRouter si commence par `sk-`. |
| `SCORER_MODEL` | Modele de scoring. |
| `QA_MODEL` | Modele Ask AI; sinon reprend `SCORER_MODEL`. |
| `OLLAMA_URL` | Endpoint Ollama fallback. |
| `OLLAMA_MODEL` | Modele Ollama. |

Comportement :

- Scoring : OpenRouter prioritaire, Ollama fallback.
- Ask AI : OpenRouter si cle valide, sinon Ollama.
- Sans OpenRouter ni Ollama accessible, le scoring retourne une erreur et l'article peut rester non score.

## Polling et anti-flood

| Variable | Description |
| --- | --- |
| `FETCH_INTERVAL_MINUTES` | Intervalle entre cycles RSS. |
| `MAX_NEW_ARTICLES_PER_FEED` | Nouveaux articles max par feed et par cycle. |
| `MAX_ARTICLE_AGE_DAYS` | Age max des articles ingestes. |
| `SCORE_DELAY_SECONDS` | Delai entre appels de scoring. |

Ces limites protegent contre les feeds trop bruyants et les couts LLM.

## Retention

| Variable | Description |
| --- | --- |
| `MAX_ARTICLES_PER_FEED` | Nombre max conserve par feed. |
| `ARTICLE_RETENTION_DAYS` | Suppression des articles anciens non bookmarkes; `0` desactive. |

Le cleanup tourne au demarrage de l'API puis toutes les 24 h.

## Local vs production

Local HTTP :

```env
HTTPS_ONLY=false
CORS_ORIGIN=
```

Production HTTPS derriere Nginx Proxy Manager :

```env
HTTPS_ONLY=true
CORS_ORIGIN=https://reader.example.com
AUTH_PASSWORD=<strong random string>
API_SECRET=<strong random string>
```

`CORS_ORIGIN` ne doit pas avoir de slash final.

