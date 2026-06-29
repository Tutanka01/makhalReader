# Vision Projet — MakhalReader

> Document parent. On itère les sous-projets depuis ici. Chaque pilier obtient ensuite
> sa propre spec détaillée → plan → implémentation. Ce document fixe **le cap**, pas les
> détails d'implémentation finaux.
>
> Date : 2026-06-18 · Statut : vision validée, sous-projets à spécifier un par un.

---

## 1. Étoile polaire

> **Moins lire. Plus savoir.**

MakhalReader n'est pas un *lecteur RSS*. C'est une **couche d'intelligence locale entre
le firehose et ton cerveau** : un système qui *métabolise* le contenu au lieu de
l'empiler.

Le problème qu'on attaque frontalement : **60 articles/jour, c'est trop.** La capacité de
lecture d'un humain est le goulot. Aujourd'hui le produit produit *plus d'entrée* que
l'utilisateur ne peut absorber. La nouvelle proposition de valeur : **réduire l'entrée,
augmenter le savoir retenu.**

### Règle de discipline (anti-bloat)

> Toute fonctionnalité qui ne sert pas « moins lire, plus savoir » est du bruit.
> On ne *rajoute* pas des features : on **réoriente l'existant** autour de l'étoile polaire,
> et on **coupe** ce qui ne s'aligne pas.

---

## 2. Positionnement & moat

Le marché se divise en deux camps, et **personne ne tient les deux bouts** :

| Camp | Exemples | Ce qu'ils font | Angle mort |
|------|----------|----------------|------------|
| Triage | Feedly + Leo, Inoreader | Filtrer/résumer pour décider quoi lire | S'arrêtent à « voici ce qui compte » |
| Capture / savoir | Readwise Reader, Matter, RemNote, Obsidian | Surligner, exporter, répétition espacée | Supposent que tu as *déjà lu* |

**Notre moat — ce que les concurrents ne peuvent pas copier :**

1. **Self-hosted, local-first, Ollama-native.** Readwise / Feedly / Matter sont tous
   cloud-SaaS. Il n'existe **aucun** lecteur technique IA, auto-hébergé, vraiment excellent.
   Notre audience (r/selfhosted, r/homelab, r/sre) *refuse* le cloud et *adore* héberger.
   → Toute fonctionnalité IA doit tourner **100 % en local** (Ollama). Le cloud (OpenRouter)
   est un accélérateur **optionnel**, jamais une dépendance.
2. **Scoring 0–10 contrastif qui apprend** du feedback 👍/👎 (profil de préférences déjà en
   place). La plupart des concurrents font du filtrage générique. À garder absolument.
3. **La synthèse cross-articles** (pilier ①) : personne ne synthétise *le flux entier*.
   Feedly résume **1** article à la fois.

Pitch d'une ligne : **« L'IA qui a tout lu pour toi — chez toi. »**

---

## 3. La boucle (le métabolisme de la connaissance)

Les trois piliers retenus forment une chaîne complète, pas trois features isolées :

```
  FIREHOSE          ① BRIEFING          ② CERVEAU            ④ RÉPÉTITION
  60 articles  →   synthèse du flux  →  savoir interrogeable  →  ça reste
                   (lire MOINS)         (savoir PLUS)            (ne plus oublier)

  └──────────────  ingérer → distiller → retenir  ──────────────┘
```

Brique transversale clé : un **pipeline de distillation** transforme un article (ou un
highlight) en **unités atomiques de connaissance** (affirmations + citation source). Cette
brique alimente **à la fois ② et ④** → on la construit une fois.

> Pilier ③ « De l'article à l'action dans ton stack » : **écarté pour l'instant** (le plus
> niche et le plus risqué). Gardé en réserve comme pari futur.

---

## 4. État existant (point de départ pour un dev)

**Backend** (6 conteneurs Docker, 1 proxy interne) :
- `poller` — feedparser + APScheduler (fetch des feeds)
- `extractor` — trafilatura / readability (texte plein + `<link rel=canonical>`)
- `scorer` — score 0–10 via Ollama **ou** OpenRouter ; produit `tags`, `summary_bullets`,
  `reason`, `reading_time` (source : `backend/scorer/prompt.py`, `scorer.py`)
- `api` — FastAPI + SQLite (WAL) ; SSE temps réel ; auth par session
- `frontend` — React 18 + Vite, PWA offline

**Tables** (source de vérité : `backend/api/database.py`) :
- `feeds`, `articles` (dont `score`, `tags_json`, `summary_bullets_json`, `reason`,
  `reading_time`, `user_feedback`, `read_at`, `bookmarked`), `highlights`, `auth_sessions`

**Briques réutilisables précieuses** : le scoring + le profil de préférences ; les
`summary_bullets` et `tags` déjà générés par article (← le Briefing se construit dessus
sans recalcul) ; les highlights (signal utilisateur curé) ; AskAIPanel (deviendra
l'interface d'interrogation du Cerveau).

### Contrainte d'architecture self-hosted

- **Moins de conteneurs, pas plus.** On *étend* les services existants (module dans
  `scorer`/`poller` + endpoints API) plutôt que d'ajouter des conteneurs. Chaque conteneur
  en plus = friction de déploiement pour l'audience self-hosted.
- **Map-reduce sur les métadonnées existantes** pour tenir dans un petit modèle local : on
  ne fourre jamais 60 articles plein-texte dans le contexte. On part des `summary_bullets`
  + `tags` + `reason` déjà produits.

---

## 5. Les sous-projets

Chacun = un cycle **spec → plan → build**, fini et solide avant le suivant.

| Pilier | Brique nouvelle | Dépend de | Effort | Ordre |
|--------|-----------------|-----------|--------|-------|
| ① Briefing | Job de synthèse cross-articles | scoring/digest existant | 🟢 Moyen | **1er** |
| ② Cerveau | Distillation + store vectoriel + RAG local | pipeline de distillation | 🟠 Gros | 2e |
| ④ Répétition | Scheduler FSRS + génération de cartes | distillation du ② | 🟡 Petit | 3e |

---

### ① Le Briefing — « ne lis pas le feed, lis la synthèse »

**Problème** : 60 articles/jour est ingérable. La capacité de lecture est le goulot.

**Ce que c'est** : la surface **principale** du produit devient un briefing généré qui lit
le flux de la fenêtre (24 h par défaut), le regroupe par thème, et rend une lecture de
~5 min + les 1–3 articles à vraiment ouvrir. Le feed brut devient un *drill-down*.

**Comportement** :
1. **Entrée** : articles de la fenêtre au-dessus d'un seuil de score (réutilise le scoring).
2. **Clustering** par thème → chaque cluster = un « sujet du jour ».
3. **Synthèse par cluster** : quelle est l'histoire, qu'est-ce qui est *neuf* vs réchauffé,
   quels 1–3 articles sont les lectures canoniques.
4. **Méta-couche** : tendances inter-clusters (« 3 sources convergent sur X »), et ce qui
   est notablement *absent/silencieux*.
5. **Sortie** : un objet *Briefing* structuré (intro 1 paragraphe ; sections = clusters
   avec synthèse + « pourquoi ça compte » + articles liés ; encart « les 3 à ouvrir » ;
   option « à zapper » pour le réchauffé).

**Approche technique (recommandée pour la v1)** :
- **Pas de nouveau conteneur.** Module de synthèse invoqué par le scheduler existant
  (APScheduler du `poller`) + endpoints API.
- **Clustering par LLM sur les métadonnées existantes** (`titre` + `tags` + `summary_bullets`
  + `score` + `reason`) en map-reduce — **pas d'embeddings au départ** (YAGNI). Ça tient
  dans un petit modèle Ollama et c'est quasi gratuit car les métadonnées existent déjà.
  *(Évolution possible : embeddings `nomic-embed-text` + clustering si la qualité l'exige.)*
- **Nouvelle table** `briefings` (`id`, `generated_at`, `window_start`, `window_end`,
  `content_json`, `model_used`).
- **Endpoints** : `GET /briefings/latest`, `POST /briefings/generate`, `GET /briefings/{id}`.
- **Frontend** : `BriefingView` comme onglet par défaut (le `Daily Digest` actuel y fusionne).

**Hors-scope v1 (YAGNI)** : briefings hebdo/mensuels ; personnalisation des sections ;
TTS/audio. Daily uniquement.

**Questions ouvertes (à trancher dans la spec ①)** :
- Cadence par défaut + configurable ? (reco : chaque matin, + bouton « régénérer »)
- Seuil d'inclusion (`score ≥ ?`).
- Clustering : LLM-grouping (reco v1) vs embeddings.
- Sort du `Daily Digest` actuel (reco : fusionné dans le Briefing, pas deux onglets).

---

### ② Le Cerveau interrogeable — l'Obsidian *agentique*

**Problème** : ce que tu lis s'évapore. Aucune capitalisation.

**Ce que c'est** : une base de connaissance personnelle **auto-construite** depuis ta
lecture, **interrogeable** en langage naturel, avec réponses synthétisées **citant ton
propre historique**. L'angle Obsidian — *sans saisie manuelle*.

**Comportement** :
1. Quand un article est **lu** (ou surligné), une étape de **distillation** extrait des
   **unités atomiques** : affirmations/faits discrets, chacun avec citation + source + tags.
2. Les unités sont **embeddées** et stockées (store vectoriel local).
3. Les **highlights** entrent comme unités prioritaires (signal curé par l'utilisateur).
4. **Interrogation** : question NL → récupération des unités pertinentes (RAG) → réponse
   synthétisée **avec citations cliquables** vers les articles d'origine.

**Approche technique** :
- **Distillation** : prompt `article|highlight → [ {claim, supporting_quote, article_id, tags} ]`.
- **Stockage** : table `knowledge_units` (`id`, `article_id`, `claim`, `quote`, `tags_json`,
  `embedding`, `created_at`). Vecteurs via **`sqlite-vec`** (extension locale, fidèle à
  l'éthique self-hosted) — ou cosine en Python si volume faible.
- **Embeddings** : Ollama `nomic-embed-text` (local).
- **RAG** : `POST /brain/query {question}` → top-k unités → synthèse → `{answer, citations}`.
- **Frontend** : la vue « Cerveau / Ask » **remplace** AskAIPanel (boîte de question +
  réponse à citations).

**Hors-scope v1 (YAGNI)** : édition manuelle libre des notes (style Obsidian) ; visualisation
du graphe de connaissance (eye-candy — la **valeur, c'est l'interrogation**, pas le joli
graphe ; à garder comme effet « wow » ultérieur).

**Questions ouvertes (spec ②)** :
- Quand distiller ? (reco : à la lecture **+** au highlight, pour borner le coût)
- Store vectoriel : `sqlite-vec` (reco) vs Python.
- Modèle d'embedding.

---

### ④ Répétition espacée — l'anti-cimetière

**Problème** : même un bon article est oublié en une semaine. *« Ta liste read-later est un
cimetière. »*

**Ce que c'est** : révision espacée de ce que tu as lu, **cartes auto-générées depuis les
unités atomiques du ②**, planifiées par **FSRS**. Au lieu de pourrir, les idées clés
resurfacent jusqu'à ce qu'elles tiennent.

**Comportement** :
1. Depuis les unités des articles à fort score (ou des highlights), générer des **prompts de
   rappel** (Q/R ou texte à trous / cloze).
2. Planifier les révisions avec **FSRS**. Une surface « Révision » présente les cartes dues.
3. Noter le rappel (again/hard/good/easy) → FSRS met à jour le calendrier.

**Approche technique** :
- **Réutilise** `knowledge_units` du ②. Table `review_cards` (`id`, `unit_id`/`article_id`,
  `question`, `answer`, état FSRS : `stability`, `difficulty`, `due`, `reps`, `lapses`,
  `created_at`).
- **FSRS** : bibliothèque open-source `py-fsrs` (locale, pas de cloud).
- **Génération** : prompt `unité → {question, answer}` ou cloze depuis `claim`+`quote`.
- **Endpoints** : `GET /review/due`, `POST /review/{card}/grade`.
- **Frontend** : vue « Révision » (UI flashcard) + badge « cartes dues ».

**Hors-scope v1 (YAGNI)** : export Anki ; cartes image. Q/R + cloze uniquement.

**Dépendance** : nécessite la distillation du ②.

---

## 6. Réorientation de l'existant (plan de dé-bloat)

| Existant | Devient |
|----------|---------|
| Daily Digest | **Fusionné dans ① Briefing** (on ne garde pas les deux) |
| AskAIPanel | **Interface d'interrogation du ② Cerveau** |
| Highlights | **Unités de connaissance prioritaires** pour ②/④ |
| Scoring + profil de préférences | **Gate** ce qui entre dans le Briefing + ce qui est distillé — à **garder** (c'est le moat) |
| Reader | Reste, mais devient le **drill-down** depuis le Briefing, plus la home |
| Stats | Garder les métriques qui *signifient* qqch (rétention, cartes tenues, unités) ; couper le vanity |
| `PaperView` vs `ReaderView` | **À auditer** : redondance possible → candidat à suppression |

---

## 7. Principes & contraintes (transverses)

- **Local-first non négociable** : chaque feature IA marche sur Ollama avec un modèle
  modeste. OpenRouter = accélérateur optionnel, jamais requis.
- **Map-reduce sur les métadonnées existantes** pour tenir dans les petits modèles.
- **Moins de conteneurs, pas plus** : on étend les services existants.
- **YAGNI féroce** : chaque cycle livre le cœur de valeur, diffère l'eye-candy (graphe,
  briefings multi-périodes, export Anki).
- **Tout sert « moins lire, plus savoir » — ou est coupé.**

---

## 8. Roadmap

1. **Cycle 1 — ① Briefing** : spec dédiée → plan → build → ship. *Transforme à lui seul le
   produit et l'identité.*
2. **Cycle 2 — ② Cerveau** : construire le pipeline de distillation + RAG local.
3. **Cycle 3 — ④ Répétition** : petit, réutilise la distillation du ②.

Chaque cycle produit sa propre spec (ex. `docs/specs/AAAA-MM-JJ-<pilier>-design.md`), son
plan, son implémentation.

> **Prochaine étape** : on ouvre le **Cycle 1** en brainstormant la spec détaillée du
> **① Briefing** (cadence, seuil, méthode de clustering, fusion du Digest, forme exacte de
> l'objet Briefing et de la vue).
