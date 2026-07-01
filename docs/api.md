# API

L'API publique est servie par `backend/api/main.py`. En production et en local navigateur, elle passe par le proxy `web` sous `/api/*` et `/auth/*`.

## Authentification

| Methode | Chemin | Description |
| --- | --- | --- |
| `POST` | `/auth/login` | Verifie le mot de passe et pose le cookie de session |
| `POST` | `/auth/logout` | Supprime la session courante |
| `GET` | `/auth/status` | Retourne `200` si la session est valide, sinon `401` |

Payload login :

```json
{
  "password": "secret",
  "remember": false
}
```

Erreurs importantes :

- `401` : mot de passe invalide ou session absente.
- `429` : trop d'echecs de login depuis la meme IP.

## Articles

| Methode | Chemin | Description |
| --- | --- | --- |
| `GET` | `/api/articles` | Liste paginee des articles |
| `GET` | `/api/articles/{article_id}` | Detail complet d'un article |
| `POST` | `/api/articles/{article_id}/read` | Marque lu |
| `POST` | `/api/articles/{article_id}/unread` | Marque non lu |
| `POST` | `/api/articles/read-all` | Marque une selection comme lue |
| `POST` | `/api/articles/{article_id}/bookmark` | Bascule le bookmark |
| `POST` | `/api/articles/{article_id}/feedback` | Enregistre like/dislike/neutre |
| `POST` | `/api/articles/{article_id}/ask` | Stream une reponse IA basee sur l'article |

Filtres usuels sur `GET /api/articles` :

- `status`: `unread`, `read`, `all`
- `sort`: `score`, `date`
- `limit`, `offset`
- `category`
- `bookmarked=true`
- `min_score`
- `search`

Payload feedback :

```json
{
  "value": 1
}
```

Valeurs : `1` pour positif, `-1` pour negatif, `0` pour retirer le feedback.

## Feeds

| Methode | Chemin | Description |
| --- | --- | --- |
| `GET` | `/api/feeds` | Liste les feeds avec compteur d'articles |
| `POST` | `/api/feeds` | Ajoute un feed |
| `DELETE` | `/api/feeds/{feed_id}` | Desactive/supprime un feed selon implementation |
| `POST` | `/api/feeds/opml` | Importe des feeds depuis OPML |

Payload creation :

```json
{
  "url": "https://example.com/feed.xml",
  "name": "Example",
  "category": "Infra"
}
```

## Digest, stats et temps reel

| Methode | Chemin | Description |
| --- | --- | --- |
| `GET` | `/api/digest` | Articles recents classes par score |
| `GET` | `/api/stats` | Statistiques de lecture |
| `GET` | `/api/stream` | Flux Server-Sent Events |

Message SSE :

```json
{
  "type": "new_article",
  "data": {
    "id": 123,
    "feed_id": 4,
    "title": "Example",
    "score": 8.4,
    "tags": ["kubernetes"],
    "summary_bullets": ["..."]
  }
}
```

Les evenements `new_article` sont emis apres persistance du score par la route
interne de scoring. Un article cree mais encore `score IS NULL` ne doit pas etre
interprete comme un nouvel article score par le flux temps reel.

## Highlights

| Methode | Chemin | Description |
| --- | --- | --- |
| `GET` | `/api/articles/{article_id}/highlights` | Liste les highlights |
| `POST` | `/api/articles/{article_id}/highlights` | Cree un highlight |
| `PUT` | `/api/articles/{article_id}/highlights/{highlight_id}` | Modifie couleur/note |
| `DELETE` | `/api/articles/{article_id}/highlights/{highlight_id}` | Supprime un highlight |

Payload creation :

```json
{
  "selected_text": "texte selectionne",
  "prefix_context": "avant",
  "suffix_context": "apres",
  "color": "yellow",
  "note": "optionnel"
}
```

Couleurs autorisees : `yellow`, `green`, `blue`, `purple`.

## Routes internes

Ces routes doivent toujours recevoir `X-Internal-Secret: <API_SECRET>`.

| Methode | Chemin | Utilise par |
| --- | --- | --- |
| `GET` | `/api/internal/feeds` | `poller` |
| `GET` | `/api/internal/feedback-examples` | `scorer` |
| `GET` | `/api/internal/articles/exists` | `poller` |
| `POST` | `/api/internal/articles` | `poller` |
| `POST` | `/api/internal/feeds/{feed_id}/fetched` | `poller` |
| `POST` | `/api/internal/scoring/claim` | `poller` scoring worker |
| `POST` | `/api/internal/articles/{article_id}/score-failed` | `poller` scoring worker |
| `GET` | `/api/internal/scoring/stats` | operations |
| `POST` | `/api/internal/scoring/requeue-failed` | operations |
| `POST` | `/api/internal/articles/{article_id}/score` | `scorer` |

Contrats internes :

- `POST /api/internal/articles` cree l'article avant le scoring et retourne
  `{"id": ..., "created": false}` pour les doublons URL/titre recent. Les
  nouveaux articles sont initialises avec `scoring_status="queued"`.
- `POST /api/internal/scoring/claim` reclame un lot d'articles `queued`/`retry`
  ou `processing` avec lock expire. La route passe les lignes en
  `processing`, incremente `score_attempts`, pose `score_locked_at`, puis
  retourne `{"items": [...]}`.
- `POST /api/internal/articles/{article_id}/score-failed` nettoie le lock et
  passe l'article en `retry` avec `next_score_attempt_at`, ou `failed` apres
  `SCORING_MAX_ATTEMPTS`.
- `POST /api/internal/scoring/requeue-failed?limit=100` remet des articles
  `failed` sans score en `queued` apres correction de configuration ou de
  modele LLM.
- `POST /api/internal/articles/{article_id}/score` est idempotent pour le meme
  article : il remplace `score`, `score_details_json`, `tags_json`,
  `summary_bullets_json` et `reason`, marque `scoring_status="done"`, renseigne
  `scored_at`, puis diffuse le SSE `new_article`.
- `score IS NULL` est le signal d'un article non score ou a relancer. Les clients
  ne doivent pas assimiler cette valeur a `0`.
- Les workers doivent journaliser leurs echecs et compter sur une relance/requeue
  plutot que recreer l'article.

## Services internes

| Service | Methode | Chemin | Description |
| --- | --- | --- | --- |
| `extractor` | `POST` | `/extract` | Extrait titre, texte, HTML, images, auteur, canonical |
| `scorer` | `POST` | `/score` | Score un article puis poste le resultat a l'API |
| `scorer` | `GET` | `/health` | Sante du service scorer |

Contrat `extractor /extract` :

- `content_text` est le champ canonique pour scoring et recherche.
- `content_html` est du HTML de lecture non fiable cote navigateur; il doit etre
  rendu seulement par les composants prevus pour cela.
- `extraction_failed=true` indique un fallback faible, pas une erreur HTTP du
  endpoint.

Contrat health/version :

- `/api/health` est public et doit rester utilisable par Docker sans auth.
- Le payload minimal historique est `{"status":"ok"}`.
- `scorer /health` expose `scoring_version`; c'est le point rapide pour verifier
  qu'un rebuild du scorer a bien pris le code de calibration courant.
- Si des metadata de build/runtime sont ajoutees, les docs operations doivent
  verifier leur coherence apres `docker compose up -d --build`.

## Routes admin

| Methode | Chemin | Description |
| --- | --- | --- |
| `DELETE` | `/api/admin/articles/broken` | Supprime des articles corrompus ou sans titre utile |
| `POST` | `/api/admin/normalize-urls` | Normalise les URLs existantes et fusionne des doublons |

Ces routes sont protegees par session, mais pas par role distinct. A utiliser avec prudence.
