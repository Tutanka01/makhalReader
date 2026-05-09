# Modele de donnees

La base est SQLite avec WAL active. Le chemin est controle par `DB_PATH`, generalement `/data/makhal.db` dans le conteneur `api`.

Source de verite actuelle : `backend/api/database.py`.

## Tables

### `feeds`

| Champ | Type | Notes |
| --- | --- | --- |
| `id` | integer | Cle primaire |
| `url` | string | Unique, URL RSS/Atom |
| `name` | string | Nom affiche |
| `category` | string | Categorie UI |
| `active` | boolean | Feed actif |
| `last_fetched` | datetime | Dernier fetch connu |

### `articles`

| Champ | Type | Notes |
| --- | --- | --- |
| `id` | integer | Cle primaire |
| `feed_id` | integer | FK vers `feeds.id` |
| `title` | string | Titre final resolu |
| `url` | string | Unique, URL normalisee/canonique |
| `published_at` | datetime | Date RSS si disponible |
| `author` | string | Auteur extrait |
| `content_html` | text | HTML lisible |
| `content_text` | text | Texte brut pour scoring/recherche |
| `images_json` | text | JSON array |
| `score` | float | Score final 0-10 |
| `score_details_json` | text | Axes et caps de scoring |
| `tags_json` | text | JSON array |
| `summary_bullets_json` | text | JSON array |
| `reason` | string | Raison lisible du score |
| `read_at` | datetime | Null si non lu |
| `bookmarked` | boolean | Bookmark utilisateur |
| `extraction_failed` | boolean | Fallback extraction faible |
| `created_at` | datetime | Creation en base |
| `title_fingerprint` | string(16) | Dedup par titre |
| `user_feedback` | integer | `1`, `-1` ou null |
| `reading_time` | integer | Minutes estimees |

Index important :

- `ix_articles_title_fp_created` sur `title_fingerprint`, `created_at`.

### `highlights`

| Champ | Type | Notes |
| --- | --- | --- |
| `id` | integer | Cle primaire |
| `article_id` | integer | FK cascade vers `articles.id` |
| `selected_text` | text | Texte selectionne |
| `prefix_context` | text | Contexte avant selection |
| `suffix_context` | text | Contexte apres selection |
| `color` | string | `yellow`, `green`, `blue`, `purple` |
| `note` | text | Note optionnelle |
| `created_at` | datetime | Creation |

Index :

- `ix_highlights_article_id`

### `auth_sessions`

| Champ | Type | Notes |
| --- | --- | --- |
| `id` | string(64) | Token de session |
| `created_at` | datetime | Creation |
| `expires_at` | datetime | Expiration, indexee |
| `last_seen` | datetime | Derniere validation |
| `user_agent` | string | Tronque a 500 caracteres |
| `remember_me` | boolean | Session longue |

## Migrations

`init_db()` appelle `Base.metadata.create_all()` puis execute des migrations additives avec `ALTER TABLE` et `CREATE INDEX IF NOT EXISTS`.

Les erreurs sont ignorees pour permettre de relancer les migrations si une colonne existe deja. C'est simple et adapte a SQLite, mais il faut eviter les migrations destructives implicites.

## Deduplication

La deduplication combine :

- URL normalisee : host en lowercase, suppression de `www.`, retrait des parametres de tracking, slash final unifie.
- URL canonique HTML si l'extractor trouve `<link rel="canonical">`.
- Fingerprint de titre sur une fenetre courte de 3 jours.

Risque connu : des titres recurrents comme "Weekly Digest" peuvent provoquer des faux positifs si leurs titres normalises se ressemblent dans la fenetre.

