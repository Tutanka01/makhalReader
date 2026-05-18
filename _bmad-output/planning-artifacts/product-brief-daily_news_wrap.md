---
title: "Product Brief: Baṣīra — Research-Oriented Intelligent Literature Monitor"
status: "complete"
created: "2026-04-22"
updated: "2026-04-22"
inputs:
  - "Session BMAD Brief + Repository Analysis (prior turn)"
  - "README.md"
  - "backend/scorer/prompt.py"
  - "backend/extractor/extractor.py"
  - "backend/api/database.py"
  - "backend/poller/main.py"
  - "docker-compose.yml"
---

# Product Brief: Baṣīra — Research-Oriented Intelligent Literature Monitor

## Executive Summary

**Baṣīra** (بَصِيرَة — Arabic for *deep insight*, *discernment*) is a self-hosted, privacy-preserving RSS reader that scores every article with an LLM before the user ever opens it. Built for a PhD-level researcher and engineer working on AI-driven Requirements Engineering (ARISE pipelines), Model-Based Systems Engineering (MBSE with Arcadia/Capella), and agentic/GraphRAG architectures, the underlying system currently operates as a DevOps-tuned triage tool. The gap is sharp: the scorer's rubric rewards production incident post-mortems and Kubernetes deep-dives, but penalises surveys, theoretical contributions, and cross-disciplinary method papers — the precise artefacts a literature review depends on.

This brief describes an **incremental augmentation** of the existing system into **Baṣīra — an AI-powered research assistant for continuous literature monitoring**. The architecture, data pipeline, and Docker topology are preserved. What changes is the intelligence layer: a research-aware scoring rubric, paper-level metadata enrichment (abstract, method, dataset, metrics, contribution type, RE classification), a local embedding index for semantic retrieval and topic clustering, a structured researcher profile replacing flat tag frequencies, and a new Literature-Review Mode that groups and synthesises related work. The result is a system that feeds the researcher's working knowledge base, accelerates literature reviews, and exports requirement-rich documents directly into ARISE-style pipelines.

## The Problem

Researchers monitoring fast-moving, cross-disciplinary fields face a brutal triage problem. A PhD working on AI for Systems Engineering must track arXiv (cs.AI, cs.SE, cs.RO), Semantic Scholar, ACL Anthology, IEEE Xplore, OpenReview, and a dozen high-signal blogs — simultaneously. Classic RSS readers show everything equally. General-purpose news readers score by virality, not research value.

**The current scorer makes this worse, not better, for research use:**

- A survey paper on GraphRAG for requirements traceability scores 3/10 ("beginner tutorial, mastered topic") — yet it is the exact state-of-the-art the researcher must engage with.
- A benchmark paper introducing the first Arcadia/Capella evaluation dataset scores 5/10 because it lacks "production incident retrospective" characteristics.
- A position paper identifying open problems in SoS interoperability scores 2/10 ("vague opinion with no technical argument").

The result: the system that should surface critical literature is actively burying it. The researcher either disables scoring (losing all triage benefit) or misses key papers. Baṣīra fixes this.

Beyond scoring, the system has no memory of what has been read, no ability to cluster related papers, no way to generate a draft literature review, and no export path for documents that are rich in formalizable requirements — the front door to ARISE pipelines.

## The Solution

Augment the existing RSS reader with a research-awareness layer, built non-disruptively on top of the existing pipeline, delivering the **Baṣīra** experience:

1. **Research-aware multi-dimensional scorer** — replaces the single DevOps rubric with a unified profile that evaluates `relevance × novelty × rigor` per article, returns a structured object (`contribution_type`, `re_document_type`, `score_meta`), and calibrates against a typed researcher profile (topics × methods × domains).

2. **Paper-aware enrichment** — extends the existing `extract_arxiv` dispatcher to handle Semantic Scholar, OpenReview, ACL Anthology, and DOI landing pages. A cheap local Ollama call extracts `methods`, `datasets`, `metrics`, and `re_document_type` from every abstract at ingest — free, local, one-shot.

3. **Local semantic retrieval** — an embedding service (Ollama `nomic-embed-text` → ChromaDB at `/data/chroma/`) indexes every article at score-time. New API endpoints expose `/related`, `/clusters`, and `/research/review`.

4. **Structured researcher profile** — a typed `research_profile` table (topics, methods, domains, avoid) replaces flat tag-frequency strings. Editable via a new UI panel; feeds the scorer's preference block with structured, reproducible context.

5. **Literature-Review Mode** — a new frontend view where the researcher enters a topic, selects a time window and rigor threshold, and receives a grouped synthesis: cluster-by-cluster comparison table, synthesis paragraphs, identified gaps, and most-citable-work recommendations. Persisted in a `literature_reviews` table.

6. **ARISE export** — a `/api/research/export-arise` endpoint filters articles by `re_document_type ∈ {elicitation, extraction, method}` and exports them as structured JSON ready for downstream requirement pipelines.

## What Makes This Different

**Privacy-first and local-first by design.** The entire enrichment pipeline — classifier, embedder, scorer — runs on Ollama. No article content leaves the machine unless the user configures OpenRouter or the university VPN server. This is non-negotiable for research that may involve pre-publication materials or proprietary system specifications.

**Grounded in the actual codebase, not a rewrite.** Every enhancement uses an existing extension point: additive SQLite migrations, the existing strategy-pattern extractor, the existing scoring pipeline, the existing Docker topology. The risk profile is that of a feature addition, not a system replacement.

**Research-purpose as a first-class concern.** The `re_document_type` classifier (elicitation / extraction / method / none) is not metadata decoration — it is the bridge to ARISE. An article tagged `re_document_type=extraction` is a document containing formalizable requirement statements; it belongs in the RE pipeline whether or not the researcher consciously curated it.

**Continuous monitoring, not periodic searching.** Unlike Semantic Scholar's alert emails or ResearchRabbit's manual sessions, Baṣīra ingests, enriches, scores, and surfaces papers automatically on every poll cycle. The researcher wakes up to a ranked, clustered, synthesis-ready reading list.

## Who This Serves

**Primary user:** A PhD-level researcher and engineer (Arona / Mohamad profile) who:
- Works across AI/MBSE/SoS/RE — genuinely cross-disciplinary, not a specialist in one area
- Reads 20–50 papers per week in monitoring mode, 100+ during an active literature review sprint
- Runs local Ollama on an M5 Max (36 GB, 2 TB) — privacy and cost control are non-negotiable
- Also has access to a university GPU Ollama server (VPN) and an OpenRouter key for cloud models
- Uses the underlying reader daily; every enhancement must not degrade the existing DevOps reading experience

**Secondary user (future):** A research group or lab that self-hosts Baṣīra as a shared literature monitor, with per-user research profiles and shared review exports.

## Success Criteria

| Signal | Target |
|---|---|
| Research-relevant articles in score ≥ 7 tier | +40% vs baseline (measured over 2-week window) |
| `re_document_type` classification macro-F1 | ≥ 0.80 on 50-item labeled set |
| Related-paper recall@10 | ≥ 0.60 on 20 seed articles with known related work |
| Literature review usefulness (self-rated 1–5) | ≥ 4.0 mean on coverage + accuracy axes |
| Ingest cost vs baseline | ≤ 2× tokens per article after full enrichment |
| DevOps article score quality (no regression) | Existing 👍/👎 accuracy within ±5% of baseline |

## Scope (v1 Augmentation)

**In scope:**
- Research-aware scoring prompt (`PROMPT_PROFILE=unified`, env-configurable)
- Structured `ScoreResult` with `contribution_type`, `re_document_type`, `score_meta_json`
- Paper handler dispatcher: Semantic Scholar, OpenReview, ACL Anthology, DOI/Crossref
- Cheap Ollama enrichment pass (abstract → `paper_meta_json`)
- Additive DB migrations (`paper_meta_json`, `score_meta_json`, `embedding_indexed`, `re_document_type`, `contribution_type`, `research_profile` table, `literature_reviews` table)
- Embedding service (Ollama → Chroma) + `/related` + `/clusters` API
- Typed researcher profile CRUD API + Settings UI
- Literature-Review Mode (frontend view + synthesis endpoint)
- ARISE export endpoint
- Admin `/rescore` endpoint for rubric changes
- `api/main.py` router split (prerequisite refactor, zero behavior change)

**Explicitly out of scope for v1:**
- Neo4j / property graph (deferred to v2 after embeddings validate clustering utility)
- Full GraphRAG global synthesis (Leiden community detection) — use HDBSCAN clusters instead
- Multi-user research profiles
- Fine-tuning any model on the user's reading history
- Mobile app / PWA changes beyond adding new view tabs

## Vision

In two to three years, **Baṣīra** becomes the researcher's **ambient knowledge infrastructure**: every paper read, highlighted, annotated, and classified flows into a queryable knowledge graph. When writing a paper section, the researcher asks "what have I read about LLM-based requirement extraction in the last 18 months?" and receives a structured synthesis with citations, gaps, and suggested related work — all grounded in their own curated reading history, not a generic web search. The ARISE pipeline receives a continuous, high-quality stream of pre-classified requirement-rich documents, eliminating the manual curation bottleneck. Baṣīra runs entirely on-premises (or on the university GPU server when heavier inference is needed), costs nothing per query, and knows more about the researcher's domain than any external service.
