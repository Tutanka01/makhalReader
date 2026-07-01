# Backend

Le backend est decoupe en quatre services Python. `api` est la source de verite applicative; `poller`, `extractor` et `scorer` sont des workers HTTP internes.

## API FastAPI

Fichiers principaux :

- `backend/api/main.py` : routes HTTP, SSE, ingestion interne, nettoyage, feeds par defaut.
- `backend/api/database.py` : modele SQLAlchemy, SQLite WAL, migrations additives.
- `backend/api/models.py` : schemas Pydantic publics et internes.
- `backend/api/auth.py` : auth par mot de passe, cookie HttpOnly et sessions persistantes.

Responsabilites :

- Initialiser SQLite et les migrations au demarrage.
- Ajouter les feeds par defaut si absents.
- Proteger les routes utilisateur par session cookie.
- Proteger les routes internes par `X-Internal-Secret`.
- Exposer articles, feeds, digest, stats, highlights et Ask AI.
- Diffuser les nouveaux articles scores via SSE.
- Nettoyer les vieux articles selon la retention configuree.

### Auth

`AUTH_PASSWORD` est obligatoire. Le mot de passe est hashe au demarrage avec bcrypt apres digest SHA-256, ce qui evite la limite bcrypt de 72 octets.

Sessions :

- cookie : `makhal_sid`
- duree courte : 24 h
- remember me : 365 jours
- stockage : table `auth_sessions`
- cookie `HttpOnly`, `SameSite=Strict`, `Secure` sauf si `HTTPS_ONLY=false`

La protection brute-force est en memoire par IP. Elle est utile pour une instance unique, mais elle se reinitialise au redemarrage et n'est pas partagee entre replicas.

## Poller

Fichier : `backend/poller/main.py`

Le poller utilise APScheduler et lance `poll_all_feeds()` toutes les `FETCH_INTERVAL_MINUTES`.

Points cles :

- attend la disponibilite de l'API avant de demarrer;
- trie les entrees RSS par date descendante;
- ignore les articles plus vieux que `MAX_ARTICLE_AGE_DAYS`;
- limite les nouveaux articles par feed avec `MAX_NEW_ARTICLES_PER_FEED`;
- normalise les URLs et retire les parametres de tracking;
- appelle extractor puis cree l'article via l'API;
- met a jour `feeds.last_fetched` apres une lecture RSS reussie;
- lance un worker de scoring durable qui reclame des lots via l'API;
- serialize les appels LLM avec un semaphore global et `SCORE_DELAY_SECONDS`;
- reporte les echecs de scoring a l'API pour backoff/retry au lieu de perdre
  l'article.

Les appels HTTP du poller vers `api`, `extractor` et `scorer` sont retentes
jusqu'a 3 fois avec backoff exponentiel. Si le scorer echoue encore, le poller
poste `/api/internal/articles/{id}/score-failed`; l'API passe l'article en
`retry` avec `next_score_attempt_at`, ou en `failed` apres
`SCORING_MAX_ATTEMPTS`. Le contrat operationnel est de ne jamais dupliquer
l'article pour relancer le scoring.

## Extractor

Fichier : `backend/extractor/extractor.py`

Endpoint principal : `POST /extract`

Strategies, dans l'ordre :

1. extraction specialisee arXiv pour les pages `/abs/`;
2. extraction Reddit via JSON public du post, avec fallback sur le contexte RSS;
3. fetch direct avec headers navigateur;
4. Readability et Trafilatura;
5. extraction Substack depuis payload HTML embarque;
6. `content:encoded` RSS;
7. resume RSS;
8. Google cache;
9. Wayback Machine;
10. fallback court sur resume RSS avec `extraction_failed=true`.

L'extractor renvoie aussi une URL canonique quand un `<link rel="canonical">` fiable est trouve. Le poller l'utilise pour ameliorer la deduplication.

### Contrat HTML

`content_text` est la reference pour le scoring, la recherche et Ask AI.
`content_html` est uniquement du HTML de lecture, issu de Readability,
Trafilatura, arXiv, Reddit ou des fallbacks RSS. L'extractor nettoie surtout la
structure lisible, resout les URLs relatives et retire certains wrappers, mais
ce champ doit rester traite comme du HTML non fiable cote UI. Tout composant qui
l'affiche doit conserver une surface restreinte et eviter d'ajouter des scripts,
handlers inline ou transformations larges sans verification visuelle.

Quand l'extraction est faible, `extraction_failed=true` signale que le contenu
vient d'un fallback court, souvent le resume RSS. Ce flag ne bloque pas le
scoring; il sert a diagnostiquer les articles peu riches.

## Scorer

Fichier : `backend/scorer/scorer.py`

Endpoint principal : `POST /score`

Le scorer :

- recupere un profil de preferences depuis l'API;
- construit un prompt avec titre, resume RSS et texte extrait;
- utilise OpenRouter si `OPENROUTER_API_KEY` commence par `sk-`;
- utilise Ollama comme fallback si `OLLAMA_URL` est configure;
- extrait un JSON depuis la reponse du modele;
- valide les axes avec Pydantic;
- calcule le score final avec `compute_final_score()`;
- poste le score, tags, bullets, raison et details vers l'API.

Axes de scoring :

- `topic_fit`
- `technical_depth`
- `operational_value`
- `strategic_value`
- `novelty`
- `noise_penalty`
- `confidence`
- `content_type`

Le champ `score_details_json` permet de comprendre pourquoi un article a ete cape ou favorise.

### Contrat de scoring durable

L'API est la source de verite du resultat de scoring. Le scorer ne modifie pas
SQLite directement : il poste sur
`POST /api/internal/articles/{article_id}/score` avec `X-Internal-Secret`.

Semantique attendue :

- `score IS NULL` signifie "article ingere mais pas encore score".
- `score IS NOT NULL` signifie "scoring termine"; `score_details_json`,
  `tags_json`, `summary_bullets_json` et `reason` doivent etre coherents avec ce
  score.
- `scoring_status` suit l'etat operationnel: `queued`, `processing`, `retry`,
  `done`, `failed`.
- Un echec scorer ne supprime pas l'article et ne doit pas creer de doublon.
- Les relances doivent etre idempotentes pour un `article_id` donne : poster un
  nouveau score remplace les champs de scoring du meme article.
- Les articles `failed` peuvent etre remis dans la file avec
  `POST /api/internal/scoring/requeue-failed?limit=100` apres correction de la
  configuration LLM.
- `score_details_json.scoring_version` permet de reperer les articles scores
  avec une ancienne calibration.

Inspection rapide depuis l'hote, sans supposer que le binaire `sqlite3` existe
dans l'image `api` :

```bash
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); print(db.execute(\"select count(*) from articles where score is null\").fetchone()[0])"
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); print(db.execute(\"select id, created_at, title from articles where score is null order by created_at desc limit 20\").fetchall())"
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); print(db.execute(\"select json_extract(score_details_json, '$.scoring_version'), count(*) from articles where score is not null group by 1 order by 1\").fetchall())"
```

## Points de vigilance

- `API_SECRET=changeme` est une valeur dangereuse en production.
- `backend/shared/database.py` diverge du modele actuel et semble etre une dette historique.
- Les routes admin sont protegees par session utilisateur, mais il n'y a pas de role admin separe.
- Le rendu HTML cote frontend depend de la qualite/sanitisation de l'extraction.
- Les services externes de fallback d'extraction peuvent etre lents ou indisponibles.
