# Sprint 6 — Automation & Productivity

**Objectif** : Automatiser les scans, ajouter des notifications, compléter le pipeline d'écriture.

**Priorité** : Haute

---

## Story 6.1: Background Task Scheduler

**Description** : Automatiser le Threat Scan, l'Author Radar, et le Citation Index via APScheduler pour qu'ils tournent sans intervention manuelle.

**ACs :**
- Ajouter APScheduler à l'api service (docker-compose + startup hook)
- Planifier Threat Scan : quotidien, fenêtre des 7 derniers jours
- Planifier Author Radar : hebdomadaire, delta detection
- Planifier Citation Index : hebdomadaire (reset-and-recompute)
- Logger le résultat de chaque run dans structlog
- Ajouter `last_run_at` dans settings pour suivi
- Les endpoints POST existants restent disponibles pour déclenchement manuel

**Fichiers :**
- `backend/api/main.py` — start_scheduler() au startup
- `backend/api/scheduler.py` — config APScheduler + jobs
- `docker-compose.yml` — dépendances

---

## Story 6.2: Notification Badges

**Description** : Afficher des badges dans la Sidebar pour les événements nécessitant attention (nouvelles menaces, deadlines imminentes, nouveaux papiers d'auteurs trackés).

**ACs :**
- Endpoint `GET /api/research/notifications` retournant :
  - `new_threats: int` — alertes depuis le dernier scan
  - `urgent_deadlines: int` — conférences avec `days_to_paper ≤ 14`
  - `new_author_papers: int` — articles depuis le dernier scan auteur
- Sidebar : badge rouge avec count sur Threats, Conferences, Authors
- `useInterval` hook : polling toutes les 60s
- Badge disparaît quand l'utilisateur clique sur la vue correspondante

**Fichiers :**
- `backend/api/routers/research.py` — GET /api/research/notifications
- `frontend/src/hooks/usePolling.ts`
- `frontend/src/components/Sidebar.tsx` — intégration badges
- `frontend/src/types.ts` — NotificationCounts interface

---

## Story 6.3: Writing Assistant Pipeline Completion

**Description** : Transformer le Writing Assistant d'un export paragraphe unique en un véritable pipeline de rédaction : gestion des highlights par section, export multi-sections, format Markdown/LaTeX.

**ACs :**
- Vue de gestion des highlights : lister tous les highlights par `thesis_section`, filtrer, éditer la section en masse
- Endpoint `POST /api/research/export-highlights/multi` : body `{sections: string[]}` → assemble toutes les sections en un document
- Export Markdown : chaque section → heading `## Section Name` + paragraphe généré
- Export LaTeX : `\section{Section Name}` + paragraphe
- Dans WriteAssistPanel : selector multi-sections + boutons d'export

**Fichiers :**
- `backend/api/routers/research.py` — multi-section endpoint
- `frontend/src/components/WriteAssistPanel.tsx` — étendu multi-sections + export
- `frontend/src/components/HighlightManager.tsx` — nouvelle vue
- `frontend/src/components/Sidebar.tsx` — nav item
- `frontend/src/App.tsx` — route

---

# Sprint 7 — Export & Advanced Features

**Objectif** : Ajouter l'export bibliographique, l'export multi-format des reviews, et le RAG cross-corpus.

**Priorité** : Moyenne

---

## Story 7.1: BibTeX Bibliography Export

**Description** : Générer une bibliographie BibTeX depuis les articles du corpus, utilisable dans Overleaf ou tout éditeur LaTeX.

**ACs :**
- Endpoint `GET /api/research/bibliography` :
  - Paramètre `since` (date), `min_score`, `contribution_type`
  - Retourne `Content-Type: text/plain; charset=utf-8` avec le fichier `.bib`
- Pour chaque article :
  - `@article{key,` avec `key = authorYearTitle[:20]`
  - `author`, `title`, `year`, `url`, `doi` (depuis paper_meta), `journal = "{Baṣīra Corpus}"`
- Extraction du DOI depuis `paper_meta_json` si disponible
- Fallback : titre comme author si pas de author détecté

**Fichiers :**
- `backend/api/bibliography.py` — générateur BibTeX
- `backend/api/routers/research.py` — GET /api/research/bibliography
- `frontend/src/components/BibliographyPanel.tsx` — UI avec filtres + bouton download

---

## Story 7.2: Lit Review Multi-Format Export

**Description** : Exporter les literature reviews en DOCX (via python-docx) et PDF (via WeasyPrint ou markdown + pandoc).

**ACs :**
- Endpoint `GET /api/research/reviews/{id}/export?format=docx` :
  - Génère un fichier DOCX structuré : title page -> topic -> chaque cluster (synthèse + table comparison + gaps)
  - Tables stylisées, titres hiérarchiques
- Endpoint `GET /api/research/reviews/{id}/export?format=pdf` :
  - Génère un PDF via conversion Markdown → HTML → PDF
- Dans LitReviewView : bouton dropdown "Export" avec DOCX / PDF / Markdown
- Le Markdown existant est conservé

**Fichiers :**
- `backend/api/litreview_exporter.py` — DOCX + PDF generation
- `backend/api/requirements.txt` — python-docx, weasyprint
- `frontend/src/components/LitReviewView.tsx` — export dropdown

---

## Story 7.3: Full-Corpus RAG Q&A

**Description** : Étendre le Ask AI existant (qui ne questionne qu'un article à la fois) pour interroger l'ensemble du corpus via RAG.

**ACs :**
- Endpoint `POST /api/research/ask` avec streaming SSE :
  - Body `{question: string, top_k: 10, window_days: 90}`
  - Embed la question → Chroma query(top_k) → récupère les articles les plus similaires
  - Construit un prompt avec les extraits + la question
  - Streame la réponse via SSE (même pattern que ask.py)
- Dans le frontend : nouveau `AskCorpusPanel.tsx` ou onglet dans WriteAssistPanel
- Inclut les citations des sources dans la réponse

**Fichiers :**
- `backend/api/routers/research.py` — POST /api/research/ask
- `frontend/src/components/AskCorpusPanel.tsx`
- `sidebase.tsx` + `App.tsx` — nav + route

---

## Résumé du Sprint

| Story | Effort estimé | Dépendances | Priorité |
|-------|---------------|-------------|----------|
| **6.1** Background Scheduler | 2-3 jours | — | 🔴 Haute |
| **6.2** Notification Badges | 2 jours | 6.1 (optionnel) | 🔴 Haute |
| **6.3** Writing Pipeline | 3-4 jours | — | 🔴 Haute |
| **7.1** BibTeX Export | 1-2 jours | — | 🟡 Moyenne |
| **7.2** Lit Review Export | 2-3 jours | — | 🟡 Moyenne |
| **7.3** Full-Corpus RAG | 3-4 jours | Epic 3 (Chroma) | 🟡 Moyenne |

**Durée totale estimée** : 2-3 semaines si tout est implémenté séquentiellement.

**Ordre recommandé** : 6.1 → 6.2 → 6.3 → 7.1 → 7.2 → 7.3
