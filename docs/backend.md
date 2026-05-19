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
- appelle extractor puis scorer;
- serialize les appels LLM avec un semaphore global et `SCORE_DELAY_SECONDS`.

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

## Points de vigilance

- `API_SECRET=changeme` est une valeur dangereuse en production.
- `backend/shared/database.py` diverge du modele actuel et semble etre une dette historique.
- Les routes admin sont protegees par session utilisateur, mais il n'y a pas de role admin separe.
- Le rendu HTML cote frontend depend de la qualite/sanitisation de l'extraction.
- Les services externes de fallback d'extraction peuvent etre lents ou indisponibles.
