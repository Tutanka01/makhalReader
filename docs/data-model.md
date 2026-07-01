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
| `last_fetched` | datetime | Dernier fetch reussi connu, si le poller le maintient |

`last_fetched` est une information operationnelle de feed, pas une preuve que
toutes les entrees ont ete extraites ou scorees. Une implementation correcte le
met a jour apres une lecture RSS reussie du feed, meme si certaines entrees sont
ensuite ignorees comme anciennes, dedupliquees ou echouent au scoring. Si la
colonne est `NULL`, traiter le feed comme jamais confirme par le poller courant.

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
| `scoring_status` | string | `queued`, `processing`, `retry`, `done`, `failed` |
| `score_attempts` | integer | Nombre de claims de scoring |
| `next_score_attempt_at` | datetime | Prochaine tentative apres backoff |
| `score_last_error` | text | Derniere erreur compacte du scorer/poller |
| `score_locked_at` | datetime | Verrou de traitement du worker |
| `scored_at` | datetime | Date de persistance du score |

Contrats importants :

- `content_text` est la source de scoring/recherche/Ask AI.
- `content_html` est du HTML de lecture produit par l'extractor; il peut venir
  d'une page distante ou d'un flux RSS et doit etre traite comme non fiable par
  le frontend.
- `score IS NULL` represente un article en attente ou en echec de scoring; il ne
  faut pas le confondre avec un score bas.
- `scoring_status` represente l'etat operationnel du pipeline. `score IS NULL`
  reste le contrat public le plus robuste pour detecter les articles non scores,
  mais `scoring_status`, `score_attempts`, `next_score_attempt_at` et
  `score_last_error` servent au diagnostic et au retry.
- `score_details_json.scoring_version`, quand present, indique la calibration du
  scorer qui a produit le score.

Index important :

- `ix_articles_title_fp_created` sur `title_fingerprint`, `created_at`.
- `ix_articles_scoring_queue` sur `scoring_status`, `next_score_attempt_at`,
  `created_at`.
- `ix_articles_feed_created` sur `feed_id`, `created_at`.

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

Les migrations additives doivent preserver les lignes existantes. Pour une queue
de scoring durable, preferer des colonnes optionnelles ou avec defaults
compatibles, afin que les anciens articles restent inspectables et relancables.

## Deduplication

La deduplication combine :

- URL normalisee : host en lowercase, suppression de `www.`, retrait des parametres de tracking, slash final unifie.
- URL canonique HTML si l'extractor trouve `<link rel="canonical">`.
- Fingerprint de titre sur une fenetre courte de 3 jours.

Risque connu : des titres recurrents comme "Weekly Digest" peuvent provoquer des faux positifs si leurs titres normalises se ressemblent dans la fenetre.

## Inspection SQLite sans CLI sqlite3

Ne pas supposer que le binaire `sqlite3` est installe dans le conteneur `api`.
Utiliser le module Python standard :

```bash
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); print(db.execute('select count(*) from articles').fetchone()[0])"
docker compose exec api python -c "import sqlite3; db=sqlite3.connect('/data/makhal.db'); print(db.execute('select id, title from articles where score is null order by created_at desc limit 10').fetchall())"
```
