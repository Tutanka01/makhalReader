# Operations

## Verification rapide

Local :

```bash
curl http://localhost/api/health
curl -i http://localhost/auth/status
docker compose ps
```

Production :

```bash
curl https://reader.example.com/api/health
curl -i https://reader.example.com/auth/status
docker compose -f docker-compose.yml -f docker-compose.npm.yml ps
```

Attendu :

- `/api/health` repond `200` avec un JSON de sante. Si le contrat de metadata
  est active, verifier aussi la presence de la version/build attendue; sinon le
  payload minimal historique est `{"status":"ok"}`.
- `/auth/status` repond `401` avant login.
- Les services `api`, `frontend`, `web`, `poller`, `extractor`, `scorer` sont running.

Checklist rebuild et derive de version :

```bash
docker compose up -d --build
docker compose ps
curl -s http://localhost/api/health
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read().decode())"
docker compose logs --tail=50 api poller extractor scorer
```

Apres un rebuild, comparer le contenu de `/api/health`, l'heure de creation des
conteneurs dans `docker compose ps` et les premieres lignes de logs. Si un
service sert encore l'ancien comportement, reconstruire explicitement le service
concerne, par exemple `docker compose up -d --build api scorer poller`.

## Logs utiles

Local :

```bash
docker compose logs -f --tail=100 web api frontend
docker compose logs -f --tail=100 poller extractor scorer
```

Production :

```bash
docker compose -f docker-compose.yml -f docker-compose.npm.yml logs -f --tail=100 web api frontend
docker compose -f docker-compose.yml -f docker-compose.npm.yml logs -f --tail=100 poller extractor scorer
```

## Sauvegarde

Tout l'etat applicatif est dans SQLite sous `/data/makhal.db`, dans le volume Docker `data`.

```bash
docker compose exec api python -c "import sqlite3; src=sqlite3.connect('/data/makhal.db'); dst=sqlite3.connect('/data/makhal.db.bak'); src.backup(dst); dst.close(); src.close()"
docker compose cp api:/data/makhal.db.bak ./makhal.db.bak
```

Note : l'image `api` est basee sur `python:3.12-slim`; elle fournit le module
Python `sqlite3`, mais pas forcement le binaire CLI `sqlite3`.

Pour la production, ajouter `-f docker-compose.yml -f docker-compose.npm.yml` aux commandes Compose.

## Restauration

```bash
docker compose cp ./makhal.db.bak api:/data/makhal.db
docker compose restart api
```

Idealement, arreter les services qui ecrivent pendant une restauration :

```bash
docker compose stop poller scorer
docker compose cp ./makhal.db.bak api:/data/makhal.db
docker compose restart api
docker compose start scorer poller
```

## Rotation du mot de passe

1. Modifier `AUTH_PASSWORD` dans `.env`.
2. Redemarrer l'API :

```bash
docker compose up -d api
```

3. Optionnel : invalider toutes les sessions existantes.

```bash
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); db.execute('DELETE FROM auth_sessions'); db.commit(); db.close()"
```

## Depannage

### L'UI charge mais login/articles ne fonctionnent pas

Cause probable : le proxy public pointe vers `frontend` au lieu de `makhal-reader-web`.

Verifier :

- cible NPM : `makhal-reader-web`
- port : `80`
- logs : `web api`

### Les articles ne sont pas scores

Verifier :

- `OPENROUTER_API_KEY` valide ou Ollama accessible;
- `SCORER_MODEL`/`OLLAMA_MODEL`;
- logs `scorer`;
- logs `poller` pour voir si le scoring est appele.

Inspecter la queue durable implicite, c'est-a-dire les articles deja stockes
mais sans score :

```bash
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); print(db.execute(\"select count(*) from articles where score is null\").fetchone()[0])"
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); rows=db.execute(\"select id, created_at, title, extraction_failed from articles where score is null order by created_at desc limit 20\").fetchall(); [print(r) for r in rows]"
```

Pour distinguer un retard normal d'un echec durable :

- si `poller` journalise `Article stored for durable scoring`, l'article est en
  file et sera traite par le worker de scoring;
- si `poller` journalise `Claimed scoring batch` puis `Scoring completed`, le
  pipeline fonctionne;
- si `poller` journalise `Scoring failed`, regarder `score_last_error`, l'erreur
  HTTP/LLM dans `scorer`, et le prochain `next_score_attempt_at`;
- si `scorer` journalise `Failed to post score to API`, verifier `API_SECRET` et
  la route interne `/api/internal/articles/{id}/score`;
- si les articles restent `score IS NULL` apres redemarrage, verifier
  `/api/internal/scoring/stats` via le reseau interne ou inspecter SQLite; ne pas
  recreer les articles a la main.

Voir les versions de calibration deja persistees :

```bash
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); rows=db.execute(\"select json_extract(score_details_json, '$.scoring_version') as version, count(*) from articles where score is not null group by version order by version\").fetchall(); [print(r) for r in rows]"
```

### Trop d'articles ou cout LLM trop eleve

Reduire :

- `FETCH_INTERVAL_MINUTES`
- `MAX_NEW_ARTICLES_PER_FEED`
- `MAX_ARTICLE_AGE_DAYS`

Augmenter :

- `SCORE_DELAY_SECONDS`

### Production : erreur `network npm_default not found`

Le reseau Docker de NPM n'a pas ce nom. Lister les reseaux :

```bash
docker network ls
```

Puis adapter `docker-compose.npm.yml` ou connecter MakhalReader au bon reseau externe.

## Checklist securite

- `AUTH_PASSWORD` fort.
- `API_SECRET` fort et different du mot de passe.
- `.env` non commite.
- `HTTPS_ONLY=true` en production.
- `CORS_ORIGIN` exact, sans slash final.
- NPM pointe vers `makhal-reader-web:80`.
- Ports `8000`, `8001`, `8002` non exposes publiquement.
