# Architecture

MakhalReader est une application composee, orientee ingestion asynchrone. Le frontend ne parle jamais directement aux services metier internes : il passe par le proxy `web`, qui route les chemins navigateur vers l'API ou vers l'UI statique.

## Vue systeme

```text
Browser / PWA
  |
  | http://localhost
  | ou https://reader.example.com via Nginx Proxy Manager
  v
web:80 (Nginx interne)
  |-- /api/*  -> api:8000
  |-- /auth/* -> api:8000
  `-- /*      -> frontend:80

poller
  -> api:8000       recupere les feeds actifs, cree les articles
  -> extractor:8001 extrait le contenu lisible
  -> scorer:8002    demande le score LLM

scorer
  -> api:8000       lit le profil de preference, poste le score final
  -> OpenRouter     si OPENROUTER_API_KEY est configure
  -> Ollama         fallback local si OLLAMA_URL est configure

api
  -> SQLite /data/makhal.db
  -> SSE /api/stream vers les clients
```

## Services

| Service | Dossier | Responsabilite |
| --- | --- | --- |
| `api` | `backend/api` | API FastAPI, auth, SQLite, feeds, articles, highlights, stats, SSE, ingestion interne |
| `poller` | `backend/poller` | Scheduler RSS, filtrage recent, deduplication, appel extractor/scorer |
| `extractor` | `backend/extractor` | Extraction HTML, arXiv, Substack, Readability, Trafilatura, RSS fallback |
| `scorer` | `backend/scorer` | Prompt LLM, parsing JSON, calibration du score, fallback OpenRouter/Ollama |
| `frontend` | `frontend` | React/Vite/Tailwind/PWA |
| `web` | `nginx/npm.conf` | Proxy interne unique pour l'app navigateur |

## Flux d'ingestion

1. `poller` attend que `api` reponde sur `/api/health`.
2. `poller` appelle `GET /api/internal/feeds` avec `X-Internal-Secret`.
3. Chaque feed est parse avec `feedparser`.
4. Les entrees sont triees par date descendante, puis filtrees par `MAX_ARTICLE_AGE_DAYS`.
5. `poller` normalise l'URL, verifie l'existence via `/api/internal/articles/exists`, puis appelle `extractor /extract`.
6. `extractor` renvoie titre, HTML, texte, images, auteur, temps de lecture et URL canonique eventuelle.
7. `poller` cree l'article via `POST /api/internal/articles`; l'API le place en
   `scoring_status="queued"`.
8. Le worker de scoring du `poller` reclame des lots via
   `POST /api/internal/scoring/claim`.
9. Pour chaque article reclame, le worker appelle `scorer /score` avec le texte
   extrait. En cas d'echec, il poste sur
   `/api/internal/articles/{id}/score-failed` pour programmer un retry ou passer
   en `failed`.
10. `scorer` construit un profil de preferences via
    `/api/internal/feedback-examples`, interroge le LLM, valide une analyse
    structuree, calcule le score final et poste le resultat sur
    `/api/internal/articles/{id}/score`.
11. `api` persiste le score, marque `scoring_status="done"` et diffuse l'article
    aux clients SSE.

Le point durable du flux est l'etape 7 : une fois l'article cree, un echec de
scoring ne perd pas l'article. La file de rattrapage operationnelle est portee
par `scoring_status`, `score_attempts`, `next_score_attempt_at` et
`score_last_error`; `score IS NULL` reste le signal public des articles non
scores.

## Flux utilisateur

- Auth : `POST /auth/login` cree une session persistante et un cookie `makhal_sid`.
- Liste : `GET /api/articles` retourne une page de `ArticleListItem`.
- Lecture : `GET /api/articles/{id}` retourne le contenu complet.
- Mutations : read/unread/bookmark/feedback/highlights modifient SQLite et le store frontend applique souvent une mise a jour optimiste.
- Temps reel : `GET /api/stream` pousse les nouveaux articles scores.
- Ask AI : `POST /api/articles/{id}/ask` stream une reponse SSE-like basee uniquement sur le contenu de l'article.

## Decisions importantes

- SQLite est centralise dans `api`; les autres services passent par des endpoints internes plutot que d'ecrire directement en base.
- Les migrations sont additives et executees au demarrage dans `init_db()`.
- Le scoring est separe en deux etapes : le LLM produit des axes, puis le code calcule le score final 0-10. Cela reduit la derive du prompt.
- Le HTML extrait est une representation de lecture, pas une source de verite
  securisee. `content_text` reste le contrat robuste pour les traitements IA.
- `score_details_json.scoring_version` est le marqueur de derive de calibration
  pour les scores deja persistes.
- Le proxy `web` est obligatoire pour que les chemins relatifs frontend (`/api/*`, `/auth/*`) fonctionnent en local comme en production.
