---
title: "Product Brief Distillate: Baṣīra"
type: llm-distillate
source: "product-brief-daily_news_wrap.md"
created: "2026-04-22"
purpose: "Token-efficient context for downstream PRD and Architecture workflows"
---

# Product Brief Distillate: Baṣīra

## Core Identity
- **System name: Baṣīra** (بَصِيرَة — Arabic for *deep insight/discernment*)
- Brownfield augmentation of the existing RSS + LLM scoring reader (6 Docker services)
- Target: research-oriented intelligent literature monitoring system
- Primary user: PhD researcher/engineer, AI-driven RE + MBSE + SoS + GraphRAG
- Constraint: NO full rewrite; additive only; local-first (Ollama); privacy-preserving

## Rejected Ideas (do not re-propose)
- Neo4j / full property graph in v1 — deferred; too heavy; validate with embeddings first
- Fine-tuning models on reading history — complexity/cost not justified in v1
- Replacing Docker topology or SQLite — preserving existing infra is a hard constraint
- Replacing current scoring pipeline — extend it, do not replace it
- Multi-user profiles in v1 — single-user focus

## Technical Constraints (hard)
- SQLite WAL only (no Postgres); additive migrations via `try/except ALTER TABLE` pattern in `init_db()`
- 6-service Docker Compose topology: api, poller, extractor, scorer, frontend, caddy — keep as-is
- Ollama must remain first-class citizen for ALL new LLM calls (embeddings + classification + scoring)
- OpenRouter/Gemini is optional (env-configurable), never required
- Content cap in scorer: currently 3000 chars — raise to 6000 (12000 for papers) via `SCORER_MAX_CHARS` env var
- `api/main.py` is 1266 LOC monolith — MUST be split into routers BEFORE adding research endpoints

## Key Technical Decisions (from codebase analysis)
- `PROMPT_PROFILE` env var selects scoring profile: `infra | research | unified` (default: `unified`)
- `ScoreResult` extended with: `contribution_type`, `re_document_type`, `novelty`, `rigor`, `relevance_to_topics`
- New DB columns (all nullable): `paper_meta_json TEXT`, `score_meta_json TEXT`, `embedding_indexed INTEGER`, `re_document_type VARCHAR(24)`, `contribution_type VARCHAR(24)`
- New DB tables: `research_profile (id, kind, label, weight, source)`, `literature_reviews (id, topic, window_days, body_json, created_at)`
- Embedder: Ollama `nomic-embed-text` → ChromaDB at `/data/chroma/` (same Docker volume as DB)
- Paper handler dispatcher pattern mirrors existing `extract_arxiv` (Strategy 0 in extractor.py)
- Cheap local classifier: 1-shot Ollama call on abstract → `paper_meta_json` (re_document_type, methods, datasets, metrics)
- `re_document_type ∈ {elicitation, extraction, method, none}` — ARISE bridge field

## Requirements Hints (captured from analysis)
- Must not degrade existing DevOps article scoring (regression test: ±5% feedback accuracy)
- Ingest cost ≤ 2× baseline tokens per article
- `re_document_type` classifier: macro-F1 ≥ 0.80 on 50-item labeled set
- Related-paper recall@10 ≥ 0.60 on 20 known seed articles
- Literature review self-rated usefulness ≥ 4.0/5 on coverage + accuracy
- Admin `/rescore?since=...` endpoint required — rubric changes must be retroactively applicable
- Story 1 (router split) is a blocker; must ship before any research endpoints

## Implementation Sequencing (from analysis)
1. Story 1: `api/main.py` → routers/ split (pure refactor, no behavior change)
2. Story 2: Prompt profile loader + unified prompt + structured ScoreResult + score_meta_json column
3. Story 3: Paper handler dispatcher + Semantic Scholar / OpenReview / ACL / DOI handlers + cheap Ollama enrichment
4. Story 4: Embedder service + Chroma + /related + clusters endpoint
5. Story 5: Typed research profile + editor UI + profile-driven preference block
6. Story 6: Literature-Review mode (UI + synthesis endpoint)
7. Story 7: ARISE export + re_document_type filter + admin rescore

## Platform & Integration Context
- Backend: Python 3.12 / FastAPI / SQLAlchemy / SQLite WAL
- Frontend: React 18 / TypeScript / Vite / Tailwind / Zustand
- **Hardware: Apple M5 Max, 36 GB RAM, 2 TB disk** — can run large local models comfortably
- **LLM stack (three tiers, priority order):**
  1. **Local Ollama** (M5 Max) — primary for enrichment, embedding, scoring fallback; free, private
  2. **University GPU server** (`https://llm.eva.univ-pau.fr/v1`, OpenAI-compatible, VPN required) — heavier inference (synthesis, lit-review), no per-token cost
  3. **OpenRouter** (Gemini / Claude) — cloud fallback, configured via `OPENROUTER_API_KEY`; used when VPN unavailable or for highest-quality scoring
- **Embedding model target:** `nomic-embed-text` (768d, runs on local Ollama, free)
- **Vector store:** ChromaDB (local, file-based, Docker volume mount)
- **University server integration:** same httpx async client pattern as OpenRouter; env var `UNI_OLLAMA_URL=https://llm.eva.univ-pau.fr/v1`; requires VPN — add `UNI_OLLAMA_AVAILABLE` health check
- New feeds needed: Semantic Scholar, ACL Anthology RSS; OpenReview RSS; IEEE TechRxiv; arXiv cs.SE, cs.RO added to DEFAULT_FEEDS

## Scope Signals (in / out / maybe)
- IN: unified scoring prompt, paper enrichment, embeddings, research profile, lit-review mode, ARISE export
- OUT v1: Neo4j, fine-tuning, multi-user, full GraphRAG global synthesis, mobile changes
- MAYBE v2: Leiden community detection, citation graph overlay, Zotero integration, shared team profiles

## Open Questions (unresolved)
- Should the embedder be a 7th Docker service or run as a background task inside `api`? (Lean: background task in api first, extract to service if CPU contention occurs)
- HDBSCAN vs spectral clustering for topic clusters — validate empirically with first 2 weeks of data
- Should `literature_reviews` be user-triggered only or also auto-generated weekly? (Start: user-triggered)
- Evaluation labeling: who labels the 50-item `re_document_type` set? (Answer: the researcher, one-time effort)
