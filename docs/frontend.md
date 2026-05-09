# Frontend

Le frontend est une application React sans routeur URL. La navigation est geree par etat local et stores Zustand.

## Stack

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Zustand
- `react-virtuoso` pour les listes virtualisees
- `lucide-react` pour les icones
- `date-fns` pour les dates
- `vite-plugin-pwa` et Workbox pour le mode PWA/offline

## Structure

| Chemin | Role |
| --- | --- |
| `frontend/src/main.tsx` | Bootstrap React |
| `frontend/src/App.tsx` | Auth gate, layout desktop/mobile, raccourcis clavier |
| `frontend/src/components` | Vues et composants UI |
| `frontend/src/store` | Stores Zustand |
| `frontend/src/hooks` | SSE, statut online, hooks articles |
| `frontend/src/types.ts` | Types partages cote UI |
| `frontend/vite.config.ts` | Vite, proxy dev, PWA/Workbox |

## Vues principales

- `LoginView` : formulaire de login.
- `ArticleList` : sidebar, filtres, recherche, digest/stats.
- `ReaderView` : lecture, progression, police, read/unread, bookmark, feedback, highlights, Ask AI.
- `DigestView` : articles recents par tiers de score.
- `StatsView` : statistiques de lecture.
- `FeedManagerPanel` : ajout/suppression/import OPML de feeds.
- `PaperView` : rendu adapte aux articles arXiv/papers.

## Stores

`useArticlesStore` gere :

- pagination avec `PAGE_SIZE=50`;
- filtres `category`, `sort`, `status`, `bookmarked`, `minScore`;
- recherche;
- selection et detail article;
- mutations optimistes read/unread/bookmark/feedback;
- insertion SSE avec `prependArticle`.

`useHighlightsStore` gere le CRUD des surlignages par article.

`useStatsStore` charge `/api/stats`.

## SSE

`useSSE` ouvre `EventSource('/api/stream')`.

Format attendu :

```json
{
  "type": "new_article",
  "data": {
    "id": 123,
    "title": "Article title"
  }
}
```

Le hook applique un backoff exponentiel jusqu'a 30 secondes et declenche un callback d'auth si le flux echoue a cause d'une session invalide.

## PWA et offline

La configuration Workbox cache :

- assets statiques;
- Google Fonts;
- `GET /api/articles`;
- `GET /api/articles/{id}`;
- `GET /api/digest`;
- `GET /api/feeds`.

Les routes `/api` sont exclues du fallback de navigation. Le mode offline permet donc surtout de relire ce qui a deja ete ouvert ou liste; les mutations restent dependantes du reseau.

## Developpement frontend

Commandes :

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run build
```

Attention : le proxy Vite cible `http://api:8000`, ce qui est naturel dans Docker. Hors Docker, il peut falloir adapter la cible si l'API tourne sur `localhost:8000`.

## Points de vigilance

- L'application n'a pas de routeur URL; refresh/back navigateur ne restaure pas une vue d'article specifique.
- `ReaderView` manipule du HTML extrait et applique les highlights dans ce HTML.
- Les mutations optimistes doivent rester coherentes avec les reponses serveur.
- Les textes et l'encodage doivent etre verifies en UTF-8, certains affichages PowerShell montrent du mojibake dans les fichiers racine.

