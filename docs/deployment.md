# Deploiement

Le fichier racine [DEPLOY.md](../DEPLOY.md) reste la reference courte de deploiement. Ce document explique surtout la topologie et les pieges.

## Compose local

Commande :

```bash
cp .env.example .env
docker compose up -d --build
```

`docker-compose.override.yml` est charge automatiquement et publie :

```text
localhost:80 -> makhal-reader-web:80
```

Le navigateur doit ouvrir :

```text
http://localhost
```

## Compose production avec Nginx Proxy Manager

Commande :

```bash
docker compose -f docker-compose.yml -f docker-compose.npm.yml up -d --build
```

Cette commande :

- n'utilise pas l'override local;
- ne publie pas de port hote;
- attache `web` au reseau externe `npm_default`;
- laisse NPM gerer les ports publics `80/443`.

Configuration NPM :

```text
Scheme: http
Forward Hostname / IP: makhal-reader-web
Forward Port: 80
Websockets Support: enabled
SSL: enabled
Force SSL: enabled
```

Point critique : NPM doit viser `makhal-reader-web`, pas `frontend`. Sinon l'UI charge, mais `/api/*` et `/auth/*` ne vont pas vers FastAPI.

## Routage interne

`nginx/npm.conf` route :

```text
/api/  -> http://api:8000
/auth/ -> http://api:8000
/      -> http://frontend:80
```

Le proxy desactive le buffering pour `/api/`, ce qui est important pour SSE et les streams.

## Ports

| Service | Port interne | Expose publiquement |
| --- | --- | --- |
| `api` | `8000` | Non |
| `extractor` | `8001` | Non |
| `scorer` | `8002` | Non |
| `frontend` | `80` | Non directement |
| `web` | `80` | Oui en local, via NPM en prod |

## Images et execution

Les images de base sont epinglees (`python:3.12.14-slim-bookworm`, `node:20.20.2-alpine3.23`, `nginx:1.30.4-alpine3.24`) et chaque contexte de build a son `.dockerignore`, pour que `.venv`, `node_modules`, `tests` et `.env` ne partent pas dans les images.

Les services backend tournent avec l'utilisateur non-root `app` (uid/gid 1000). L'entrypoint de `api` demarre en root uniquement pour corriger le proprietaire du volume `/data` existant, puis abandonne les privileges avec `setpriv` : les volumes crees par les anciennes images root continuent de fonctionner sans intervention manuelle.

Les logs Docker utilisent le driver `json-file`, plafonnes a 10 Mo x 3 fichiers par conteneur via l'ancre `x-logging` de `docker-compose.yml`. Modifier cette ancre pour ajuster la retention.

## Caddy

Le dossier `caddy/` est present et contient une configuration alternative, mais la stack Compose actuelle utilise `nginx/npm.conf` et Nginx Proxy Manager. Ne pas supposer que Caddy est actif sans verifier les fichiers Compose.

