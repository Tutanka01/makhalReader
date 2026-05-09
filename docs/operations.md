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

- `/api/health` repond `200`.
- `/auth/status` repond `401` avant login.
- Les services `api`, `frontend`, `web`, `poller`, `extractor`, `scorer` sont running.

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
docker compose exec api sqlite3 /data/makhal.db ".backup /data/makhal.db.bak"
docker compose cp api:/data/makhal.db.bak ./makhal.db.bak
```

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
docker compose exec api sqlite3 /data/makhal.db "DELETE FROM auth_sessions;"
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

