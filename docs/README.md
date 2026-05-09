# Documentation MakhalReader

Ce dossier regroupe la documentation technique du projet. Il complete le README racine avec des documents plus operationnels pour comprendre, modifier et exploiter l'application.

## Carte rapide

- [Architecture](architecture.md) : vue systeme, services Docker et flux principaux.
- [Backend](backend.md) : API FastAPI, poller RSS, extractor, scorer et auth.
- [Frontend](frontend.md) : React, Zustand, PWA, SSE et structure de l'interface.
- [API](api.md) : endpoints publics, internes et contrats importants.
- [Modele de donnees](data-model.md) : tables SQLite, champs et migrations additives.
- [Configuration](configuration.md) : variables d'environnement et valeurs sensibles.
- [Deploiement](deployment.md) : local, production avec Nginx Proxy Manager, routage.
- [Operations](operations.md) : sauvegarde, restauration, verification, depannage.
- [Developpement](development.md) : workflow local, commandes, conventions et points de vigilance.

## Resume du projet

MakhalReader est un lecteur RSS auto-heberge qui ingere des flux techniques, extrait le contenu lisible, le score avec un LLM, puis expose une interface de lecture rapide avec digest, recherche, surlignages, statistiques, PWA offline et mises a jour temps reel.

La stack actuelle est composee de six services Docker :

- `api` : FastAPI, auth, SQLite, endpoints publics et internes.
- `poller` : ingestion RSS planifiee.
- `extractor` : extraction du contenu HTML et metadata.
- `scorer` : scoring LLM via OpenRouter ou Ollama.
- `frontend` : React/Vite servi par Nginx.
- `web` : proxy Nginx interne qui route `/api`, `/auth` et l'UI.

## Regles de maintenance

- Le proxy public doit viser `makhal-reader-web:80`, jamais `frontend` directement.
- `AUTH_PASSWORD` et `API_SECRET` doivent etre forts en production.
- Le stockage applicatif vit dans le volume Docker `data`, sous `/data/makhal.db`.
- Les routes `/api/internal/*` utilisent `X-Internal-Secret`; les routes utilisateur utilisent la session cookie.
- Le modele de donnees principal est dans `backend/api/database.py`. Le dossier `backend/shared` semble ancien et ne doit pas etre pris comme source de verite sans verification.

