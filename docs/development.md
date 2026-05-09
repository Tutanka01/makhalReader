# Developpement

## Prerequis

Le chemin le plus fiable est Docker Compose, car les services se referencent par noms Docker (`api`, `extractor`, `scorer`).

```bash
cp .env.example .env
docker compose up -d --build
```

Pour du local HTTP, utiliser :

```env
HTTPS_ONLY=false
CORS_ORIGIN=
```

## Commandes utiles

Backend via Docker :

```bash
docker compose logs -f api
docker compose logs -f poller
docker compose restart api
```

Frontend seul :

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run build
```

Attention : `vite.config.ts` proxifie `/api` vers `http://api:8000`. Si Vite tourne hors reseau Docker, adapter temporairement la cible ou passer par `web`.

## Workflow de modification

1. Identifier le service proprietaire du comportement.
2. Verifier le contrat API ou le type TypeScript correspondant.
3. Modifier la couche la plus proche du comportement.
4. Garder la compatibilite avec les donnees SQLite existantes.
5. Tester au minimum le typecheck frontend ou le demarrage Compose selon la zone modifiee.

## Conventions existantes

- Backend : FastAPI + Pydantic + SQLAlchemy.
- Migrations : additives au demarrage dans `init_db()`.
- API interne : header `X-Internal-Secret`.
- Frontend : stores Zustand, fetch relatif, composants fonctionnels React.
- UI : pas de router URL, navigation par etat.
- PWA : Workbox configure dans `vite.config.ts`.

## Ajouter un champ article

Verifier et modifier :

1. `backend/api/database.py` : colonne SQLAlchemy + migration additive.
2. `backend/api/models.py` : schema Pydantic public/interne.
3. `backend/api/main.py` : creation, serialization, SSE si necessaire.
4. `frontend/src/types.ts` : type Article/ArticleListItem.
5. Store ou composant frontend consommateur.
6. Documentation `docs/data-model.md` et `docs/api.md` si expose.

## Ajouter un endpoint utilisateur

Checklist :

- proteger avec la dependance de session;
- retourner un schema Pydantic stable;
- gerer `404`, `401` et erreurs de validation;
- mettre a jour les stores/hooks frontend;
- documenter dans `docs/api.md`.

## Ajouter une route interne

Checklist :

- exiger `X-Internal-Secret`;
- ne pas l'exposer via le frontend;
- journaliser les erreurs cote worker;
- documenter quel service l'appelle.

## Tests et verification

Il n'y a pas de suite de tests evidente dans le depot actuel. Les verifications pratiques sont donc :

```bash
cd frontend
npm run typecheck
npm run build
```

Et cote Compose :

```bash
docker compose up -d --build
curl http://localhost/api/health
docker compose logs --tail=100 api poller scorer extractor
```

## Dette connue

- `backend/shared/database.py` semble diverger du modele API actuel.
- Les routes admin n'ont pas de role separe.
- La protection brute-force est locale au processus.
- Le frontend n'a pas de routing URL.
- Le rendu HTML extrait doit rester surveille, surtout avec les highlights et `dangerouslySetInnerHTML`.

