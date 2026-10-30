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
| `frontend/src/App.tsx` | Auth gate, layout unique compact/medium/wide, historique du lecteur, raccourcis clavier |
| `frontend/src/hooks/useLayout.ts` | Choix du layout selon la largeur disponible |
| `frontend/src/format.ts` | Dates courtes/longues en francais, hote d'une URL |
| `frontend/src/scoreDetails.ts` | Raison de score nettoyee, axes et plafonds du scorer |
| `frontend/src/components` | Vues et composants UI |
| `frontend/src/store` | Stores Zustand |
| `frontend/src/hooks` | SSE, statut online, hooks articles |
| `frontend/src/types.ts` | Types partages cote UI |
| `frontend/vite.config.ts` | Vite, proxy dev, PWA/Workbox |

## Vues principales

- `LoginView` : formulaire de login.
- `ArticleList` : liste virtualisee, missions, filtres, recherche, bandeau de scoring en cours.
- `ArticleCard` : carte d'article (jauge de signal, source, age court, extrait, swipe lu/favori).
- `ReaderView` : lecture, progression, reglages « Aa » (taille, Lora/Inter), read/unread, bookmark, carte « Analyse IA » (resume, raison, detail du score, feedback), highlights, Ask AI, article suivant.
- `ShortcutsDialog` : aide des raccourcis clavier (`?`).
- `DigestView` : articles recents par tiers de score.
- `StatsView` : statistiques de lecture.
- `FeedManagerPanel` : ajout/suppression/import OPML de feeds.
- `PaperView` : rendu adapte aux articles arXiv/papers.

## Layouts

Un seul arbre de composants, trois layouts choisis par `useLayout` selon la largeur :

| Layout | Largeur | Appareils typiques | Comportement |
| --- | --- | --- | --- |
| `compact` | < 768 px | iPhone | En-tete + barre d'onglets ; liste ou lecteur plein ecran. |
| `medium` | 768–1023 px | iPad portrait, Split View | Rail de navigation ; liste pleine largeur, le lecteur la recouvre, la liste reste accessible en slide-over (`[`). |
| `wide` | ≥ 1024 px | iPad paysage, desktop | Rail + liste epinglee (masquable avec `[`) + lecteur. |

La liste reste montee dans tous les modes (seul son placement change) : position de scroll, pages chargees et recherche survivent a l'ouverture d'un article. Sur `compact`/`medium`, ouvrir un article pousse une entree d'historique : le geste retour d'iOS, le bouton retour Android ou navigateur referment le lecteur.

Tactile : variantes Tailwind `touch:` (`pointer: coarse`, cibles agrandies) et `can-hover:` ; `hoverOnlyWhenSupported` evite les survols colles sur iPad ; les champs passent a 16 px sur tactile pour empecher le zoom iOS ; safe areas via `env(safe-area-inset-*)` ; hauteur en `100dvh`.

## Design tokens

Les couleurs sont definies dans `src/index.css` en canaux RGB (`--c-accent-blue: 139 184 255`) et exposees a Tailwind comme `rgb(var(--c-…) / <alpha-value>)`. C'est indispensable pour que les modificateurs d'opacite (`bg-accent-blue/12`, `border-score-high/30`) soient generes : avec des variables hexadecimales, Tailwind les supprime silencieusement et un `border` nu retombe sur un contour blanc. Les alias `--color-*` restent disponibles pour le CSS et les styles inline. Un `border` sans couleur utilise `--color-border-default`. `on-accent` donne la couleur de texte lisible sur un fond `accent-blue` dans chaque theme.

Score : `ScoreBadge` (`src/components/ui.tsx`) affiche une jauge de signal a 4 barres + la note (bandes 8+ / 5+ / reste). Sans score et tant que `scoring_status` n'est pas `failed`, les barres balaient (« evaluation en cours ») au lieu d'afficher un vide.

## Stores

`useArticlesStore` gere :

- pagination avec `PAGE_SIZE=50`;
- filtres `category`, `sort`, `status`, `bookmarked`, `minScore`, `lens`;
- recherche;
- selection et detail article;
- mutations optimistes read/unread/bookmark/feedback;
- insertion SSE avec `upsertArticle` : un article deja affiche (liste, recherche ou lecteur) recoit en place les champs du scorer (score, tags, resume, raison, statut) sans toucher a l'etat local lu/favori/feedback ; un article inconnu est ajoute en tete s'il correspond aux filtres.

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
    "title": "Article title",
    "score": 7.2,
    "scoring_status": "done"
  }
}
```

L'API emet `new_article` quand le scorer a fini un article. La plupart du temps l'article est deja a l'ecran avec un score en attente : `upsertArticle` le met a jour en place, le score apparait sans rechargement.

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

Le proxy Vite (`/api`, `/auth`) cible `http://api:8000`, ce qui est naturel dans Docker. Hors Docker, avec la stack Compose lancee :

```bash
VITE_PROXY_TARGET=http://localhost npm run dev
```

puis ouvrir `http://localhost:5173` (la session `localhost` est partagee avec `web`).

## Points de vigilance

- L'application n'a pas de routeur URL; refresh/back navigateur ne restaure pas une vue d'article specifique.
- `ReaderView` manipule du HTML extrait et applique les highlights dans ce HTML.
- Les mutations optimistes doivent rester coherentes avec les reponses serveur.
- Les textes et l'encodage doivent etre verifies en UTF-8, certains affichages PowerShell montrent du mojibake dans les fichiers racine.
