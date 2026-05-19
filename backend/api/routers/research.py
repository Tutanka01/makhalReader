"""Research API router — Stories 3.2–3.4 (clusters, profile, literature review).

All heavy imports (hdbscan, numpy, chromadb) are deferred inside endpoint
functions so the API service starts even if these packages are absent.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import require_session
from fastapi.responses import StreamingResponse

from database import (
    Article,
    Feed,
    Highlight,
    LiteratureReview,
    NoveltyAlert,
    ResearchProfile,
    ThesisContribution,
    TrackedAuthor,
    get_db,
    get_setting,
)
from models import (
    AriseArticleOut,
    AriseExportRequest,
    AuthorScanResponse,
    CitationIndexResult,
    CitationStatsOut,
    ClusterOut,
    ComparisonRow,
    ConferenceBookmark,
    ConferenceOut,
    ExternalPaper,
    ExternalReviewCreate,
    ExternalReviewOut,
    HighlightExportOut,
    HighlightExportRequest,
    HighlightOut,
    LiteratureReviewCreate,
    LiteratureReviewOut,
    LiteratureReviewSummaryOut,
    NoveltyAlertOut,
    ResearchProfileEntry,
    ResearchProfileUpsert,
    ReviewClusterOut,
    SourceArticle,
    ThesisContributionOut,
    ThesisContributionUpdate,
    TopCitedItem,
    TrackedAuthorOut,
    ThreatScanResponse,
    _VALID_THESIS_SECTIONS,
    build_arise_row,
)
from routers.articles import ARISE_RE_DOCUMENT_TYPES

router = APIRouter(prefix="/api/research", tags=["research"])
_auth = Depends(require_session)

logger = structlog.get_logger().bind(service="research")

_NOT_ENOUGH_ARTICLES = (
    "Not enough indexed articles match the criteria. Try a broader topic or lower rigor threshold."
)
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
_OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


def _article_rigor(article: Article) -> float:
    try:
        meta = json.loads(article.score_meta_json or "{}")
        r = meta.get("rigor")
        if r is None:
            return 0.0
        return float(r)
    except (TypeError, ValueError):
        return 0.0


async def _embed_topic_text(topic: str) -> List[float]:
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            f"{_OLLAMA_URL}/api/embeddings",
            json={"model": _OLLAMA_EMBED_MODEL, "prompt": topic.strip()[:4000]},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embedding"]


def _build_cluster_user_block(articles: List[Article], max_chars: int = 8000) -> str:
    lines: List[str] = []
    for a in articles:
        bullets: List[str] = []
        try:
            bullets = json.loads(a.summary_bullets_json or "[]")[:3]
        except Exception:
            pass
        tags: List[str] = []
        try:
            tags = json.loads(a.tags_json or "[]")[:8]
        except Exception:
            pass
        abstract = ""
        if a.paper_meta_json:
            try:
                pm = json.loads(a.paper_meta_json)
                abstract = (pm.get("abstract") or "")[:600]
            except Exception:
                pass
        chunk = (
            f"---\nID: {a.id}\nTitle: {a.title}\nURL: {a.url}\n"
            f"Score: {a.score}\nTags: {', '.join(tags)}\n"
            f"Summary bullets: {'; '.join(bullets)}\nAbstract excerpt: {abstract}\n"
        )
        lines.append(chunk)
    text = "\n".join(lines)
    return text[:max_chars]


def _centroid_title(articles: List[Article], matrix) -> str:
    import numpy as np  # noqa: PLC0415
    centroid = matrix.mean(axis=0)
    distances = np.linalg.norm(matrix - centroid, axis=1)
    nearest_idx = int(np.argmin(distances))
    return articles[nearest_idx].title


def _normalize_llm_cluster(
    raw: Dict[str, Any],
    cluster_label: str,
    article_ids: List[int],
    article_titles: List[str],
) -> ReviewClusterOut:
    synthesis = str(raw.get("synthesis") or "").strip()
    rows_in = raw.get("comparison_table") or []
    rows: List[ComparisonRow] = []
    if isinstance(rows_in, list):
        for row in rows_in[:20]:
            if not isinstance(row, dict):
                continue
            rows.append(ComparisonRow(
                work=str(row.get("work") or ""),
                method=str(row.get("method") or ""),
                dataset=str(row.get("dataset") or ""),
                key_result=str(row.get("key_result") or ""),
            ))
    gaps_in = raw.get("gaps") or []
    gaps: List[str] = []
    if isinstance(gaps_in, list):
        for g in gaps_in[:3]:
            gaps.append(str(g).strip())
    top_cite = str(raw.get("top_cite") or "").strip()
    return ReviewClusterOut(
        cluster_label=cluster_label,
        synthesis=synthesis,
        comparison_table=rows,
        gaps=gaps,
        top_cite=top_cite,
        article_ids=article_ids,
        article_titles=article_titles,
    )


@router.get("/clusters", response_model=List[ClusterOut])
async def get_clusters(
    window_days: int = Query(default=14, ge=1, le=90),
    min_size: int = Query(default=3, ge=2, le=20),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return HDBSCAN cluster summaries for embedded articles in the last window_days.

    Returns [] (not an error) when:
    - Fewer than min_size articles are embedded in the window
    - All articles are classified as noise by HDBSCAN
    - ChromaDB is unavailable
    - Any other exception (logged as warning)
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        articles = (
            db.query(Article)
            .filter(Article.embedding_indexed == 1, Article.created_at >= cutoff)
            .all()
        )
        if len(articles) < min_size:
            return []

        # Deferred import — must never be at module top-level
        from embedder import _get_chroma  # noqa: PLC0415

        collection = _get_chroma()
        if collection.count() == 0:
            return []

        ids = [str(a.id) for a in articles]
        chroma_result = collection.get(ids=ids, include=["embeddings"])

        # Build id → vector map (Chroma may be missing some IDs)
        id_to_vector: dict = {}
        for chroma_id, emb in zip(chroma_result["ids"], chroma_result["embeddings"]):
            id_to_vector[int(chroma_id)] = emb

        valid_articles = [a for a in articles if a.id in id_to_vector]
        if len(valid_articles) < min_size:
            return []

        # Heavy scientific imports — deferred to avoid startup cost + allow graceful fail
        import hdbscan as _hdbscan  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        vectors = [id_to_vector[a.id] for a in valid_articles]
        matrix = np.array(vectors, dtype=np.float32)

        labels = _hdbscan.HDBSCAN(min_cluster_size=min_size).fit_predict(matrix)

        clusters: List[ClusterOut] = []
        for cluster_id in sorted(set(labels)):
            if cluster_id == -1:  # noise — excluded per AC 2
                continue

            mask = labels == cluster_id
            cluster_articles = [a for a, m in zip(valid_articles, mask) if m]
            cluster_vectors = matrix[mask]

            # Centroid title = article whose embedding is nearest to cluster mean
            centroid = cluster_vectors.mean(axis=0)
            distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
            nearest_idx = int(np.argmin(distances))
            centroid_title = cluster_articles[nearest_idx].title

            # Top tags: aggregate tag frequencies across all cluster articles
            tag_counts: dict = {}
            for a in cluster_articles:
                for tag in json.loads(a.tags_json or "[]"):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            top_tags = [t for t, _ in sorted(tag_counts.items(), key=lambda x: -x[1])[:5]]

            clusters.append(ClusterOut(
                cluster_id=int(cluster_id),  # cast numpy.int64 → Python int for JSON
                size=len(cluster_articles),
                centroid_title=centroid_title,
                top_tags=top_tags,
                article_ids=[a.id for a in cluster_articles],
            ))

        logger.info("clusters_computed", n_clusters=len(clusters), window_days=window_days,
                    n_articles=len(valid_articles))
        return clusters

    except Exception as e:
        logger.warning("cluster_endpoint_failed", error=str(e))
        return []


# ── Research Profile endpoints (Story 3.3) ────────────────────────────────────

def _profile_to_entry(row: ResearchProfile) -> ResearchProfileEntry:
    return ResearchProfileEntry(
        id=row.id,
        kind=row.kind,
        label=row.label,
        weight=row.weight,
        source=row.source,
    )


@router.get("/profile", response_model=List[ResearchProfileEntry])
async def get_profile(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return all researcher profile entries ordered by kind then weight DESC."""
    rows = (
        db.query(ResearchProfile)
        .order_by(ResearchProfile.kind, ResearchProfile.weight.desc())
        .all()
    )
    return [_profile_to_entry(r) for r in rows]


@router.put("/profile", response_model=List[ResearchProfileEntry])
async def put_profile(
    payload: ResearchProfileUpsert,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Upsert profile entries. weight==0 deletes the entry.

    Uses INSERT OR REPLACE via SQLAlchemy merge on the unique constraint so
    a second call with the same (kind, label) updates the existing row.
    """
    for entry in payload.entries:
        norm_label = entry.label.strip().lower()
        if not norm_label:
            continue

        existing = (
            db.query(ResearchProfile)
            .filter(ResearchProfile.kind == entry.kind, ResearchProfile.label == norm_label)
            .first()
        )

        if entry.weight == 0:
            if existing:
                db.delete(existing)
        else:
            if existing:
                existing.weight = entry.weight
                existing.source = entry.source
            else:
                db.add(ResearchProfile(
                    kind=entry.kind,
                    label=norm_label,
                    weight=entry.weight,
                    source=entry.source,
                ))

    db.commit()
    rows = (
        db.query(ResearchProfile)
        .order_by(ResearchProfile.kind, ResearchProfile.weight.desc())
        .all()
    )
    logger.info("profile_updated", n_entries=len(rows))
    return [_profile_to_entry(r) for r in rows]


# ── Literature review (Story 3.4) ─────────────────────────────────────────────


@router.post("/review", response_model=LiteratureReviewOut)
async def post_literature_review(
    payload: LiteratureReviewCreate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Embed topic → Chroma top-50 → rigor/window filter → HDBSCAN → per-cluster LLM → persist."""
    topic = payload.topic.strip()
    window_days = payload.window_days
    min_rigor = payload.min_rigor
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    try:
        topic_vector = await _embed_topic_text(topic)
    except Exception as e:
        logger.warning("lit_review_embed_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Could not embed topic; check OLLAMA_URL and OLLAMA_EMBED_MODEL.",
        ) from e

    try:
        from embedder import _get_chroma  # noqa: PLC0415

        collection = _get_chroma()
        n_coll = collection.count()
        if n_coll == 0:
            raise HTTPException(status_code=422, detail=_NOT_ENOUGH_ARTICLES)
        n_query = min(100, max(1, n_coll))
        qres = collection.query(
            query_embeddings=[topic_vector],
            n_results=n_query,
            include=["distances"],
        )
        raw_ids = (qres.get("ids") or [[]])[0]
        chroma_order_ids: List[int] = []
        for sid in raw_ids:
            try:
                chroma_order_ids.append(int(sid))
            except (TypeError, ValueError):
                continue
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("lit_review_chroma_query_failed", error=str(e))
        raise HTTPException(status_code=422, detail=_NOT_ENOUGH_ARTICLES) from e

    if not chroma_order_ids:
        raise HTTPException(status_code=422, detail=_NOT_ENOUGH_ARTICLES)

    id_set = set(chroma_order_ids)
    db_articles = (
        db.query(Article)
        .filter(
            Article.id.in_(id_set),
            Article.embedding_indexed == 1,
            Article.created_at >= cutoff,
        )
        .all()
    )
    by_id = {a.id: a for a in db_articles}

    ordered: List[Article] = []
    for aid in chroma_order_ids:
        a = by_id.get(aid)
        if a is None:
            continue
        if _article_rigor(a) >= min_rigor:
            ordered.append(a)

    if len(ordered) < 3:
        raise HTTPException(status_code=422, detail=_NOT_ENOUGH_ARTICLES)

    try:
        from embedder import _get_chroma  # noqa: PLC0415

        collection = _get_chroma()
        ids_str = [str(a.id) for a in ordered]
        got = collection.get(ids=ids_str, include=["embeddings"])
        id_to_emb: Dict[int, List[float]] = {}
        for cid, emb in zip(got["ids"], got["embeddings"]):
            if emb is not None:
                id_to_emb[int(cid)] = emb
    except Exception as e:
        logger.warning("lit_review_chroma_get_failed", error=str(e))
        raise HTTPException(status_code=422, detail=_NOT_ENOUGH_ARTICLES) from e

    with_vectors: List[Tuple[Article, List[float]]] = []
    for a in ordered:
        emb = id_to_emb.get(a.id)
        if emb is not None:
            with_vectors.append((a, emb))
    if len(with_vectors) < 3:
        raise HTTPException(status_code=422, detail=_NOT_ENOUGH_ARTICLES)

    articles_v = [t[0] for t in with_vectors]
    import numpy as np  # noqa: PLC0415
    import hdbscan as _hdbscan  # noqa: PLC0415

    matrix = np.array([t[1] for t in with_vectors], dtype=np.float32)
    labels = _hdbscan.HDBSCAN(min_cluster_size=3).fit_predict(matrix)

    cluster_groups: List[Tuple[str, List[Article]]] = []
    non_noise = {int(x) for x in labels if int(x) != -1}
    if not non_noise:
        lbl = topic[:80] if topic else "Topic"
        cluster_groups.append((lbl, articles_v))
    else:
        for cluster_id in sorted(non_noise):
            mask = labels == cluster_id
            cluster_articles = [a for a, m in zip(articles_v, mask) if m]
            cluster_matrix = matrix[mask]
            clabel = _centroid_title(cluster_articles, cluster_matrix)
            cluster_groups.append((clabel, cluster_articles))

    from lit_review_llm import synthesize_cluster_json  # noqa: PLC0415

    cluster_payloads: List[ReviewClusterOut] = []
    for clabel, members in cluster_groups:
        user_block = _build_cluster_user_block(members)
        member_ids = [a.id for a in members]
        member_titles = [a.title for a in members]
        try:
            raw = await synthesize_cluster_json(clabel, user_block)
            cluster_payloads.append(_normalize_llm_cluster(raw, clabel, member_ids, member_titles))
        except Exception as e:
            logger.warning("lit_review_cluster_llm_failed", cluster=clabel, error=str(e))
            cluster_payloads.append(
                ReviewClusterOut(
                    cluster_label=clabel,
                    synthesis="[Synthesis unavailable — LLM error]",
                    comparison_table=[],
                    gaps=[],
                    top_cite="",
                    article_ids=member_ids,
                    article_titles=member_titles,
                )
            )

    body_list = [c.model_dump(mode="json") for c in cluster_payloads]
    row = LiteratureReview(
        topic=topic,
        window_days=window_days,
        min_rigor=min_rigor,
        body_json=json.dumps(body_list),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info("literature_review_saved", review_id=row.id, n_clusters=len(cluster_payloads))
    return LiteratureReviewOut(
        id=row.id,
        topic=row.topic,
        window_days=row.window_days,
        min_rigor=row.min_rigor,
        clusters=cluster_payloads,
        created_at=row.created_at,
    )


@router.get("/reviews", response_model=List[LiteratureReviewSummaryOut])
async def list_literature_reviews(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    rows = (
        db.query(LiteratureReview)
        .order_by(LiteratureReview.created_at.desc())
        .all()
    )
    return [
        LiteratureReviewSummaryOut(
            id=r.id,
            topic=r.topic,
            window_days=r.window_days,
            min_rigor=r.min_rigor,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/reviews/{review_id}", response_model=LiteratureReviewOut)
async def get_literature_review(
    review_id: int,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    row = db.query(LiteratureReview).filter(LiteratureReview.id == review_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        raw_clusters = json.loads(row.body_json or "[]")
    except json.JSONDecodeError:
        raw_clusters = []
    clusters: List[ReviewClusterOut] = []
    for item in raw_clusters:
        if not isinstance(item, dict):
            continue
        try:
            clusters.append(ReviewClusterOut.model_validate(item))
        except Exception:
            continue
    return LiteratureReviewOut(
        id=row.id,
        topic=row.topic,
        window_days=row.window_days,
        min_rigor=row.min_rigor,
        clusters=clusters,
        created_at=row.created_at,
    )


def _build_external_paper_block(papers: List[dict], max_chars: int = 12000) -> str:
    lines: List[str] = []
    for i, p in enumerate(papers, 1):
        abstract = (p.get("abstract") or "")[:400]
        authors = ", ".join((p.get("authors") or []))[:80]
        lines.append(
            f"[{i}] {p.get('title', '')}\n"
            f"Authors: {authors}\n"
            f"Year: {p.get('year') or 'n/a'} | Citations: {p.get('citation_count', 0)} | Venue: {p.get('venue') or 'n/a'}\n"
            f"Abstract: {abstract}\n"
        )
    return "\n".join(lines)[:max_chars]


@router.post("/external-review", response_model=ExternalReviewOut)
async def post_external_review(
    payload: ExternalReviewCreate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Search Semantic Scholar → OpenAlex fallback → rerank → LLM state-of-the-art synthesis."""
    from external_review import rerank_papers, search_openalex, search_semantic_scholar
    from lit_review_llm import synthesize_external_review_json

    topic = payload.topic.strip()
    min_year = payload.min_year

    papers = await search_semantic_scholar(topic, limit=30, min_year=min_year)
    source = "semantic_scholar"

    if len(papers) < 8:
        logger.info("ss_thin_falling_back", n_ss=len(papers), topic=topic)
        oa_papers = await search_openalex(topic, limit=30, min_year=min_year)
        if oa_papers:
            if papers:
                ss_titles = {p["title"].lower() for p in papers}
                deduped = [p for p in oa_papers if p["title"].lower() not in ss_titles]
                papers = papers + deduped
                source = "merged" if deduped else "semantic_scholar"
            else:
                papers = oa_papers
                source = "openalex"

    if len(papers) < 3:
        raise HTTPException(
            status_code=422,
            detail="Not enough papers found. Try a broader topic or lower min_year.",
        )

    ranked = rerank_papers(papers)[: payload.max_results]
    paper_block = _build_external_paper_block(ranked)

    try:
        raw = await synthesize_external_review_json(topic, paper_block)
    except Exception as e:
        logger.warning("external_review_synthesis_failed", error=str(e))
        raise HTTPException(status_code=503, detail="LLM synthesis failed — try again shortly.")

    paper_models = [
        ExternalPaper(
            title=p["title"],
            abstract=(p.get("abstract") or "")[:600],
            authors=p.get("authors") or [],
            year=p.get("year") or None,
            citation_count=p.get("citation_count") or 0,
            venue=p.get("venue") or "",
            url=p.get("url") or "",
            source=p.get("source") or "",
            relevance_score=p.get("relevance_score") or 0.0,
        )
        for p in ranked
    ]
    comp_rows = [
        ComparisonRow(
            work=str(row.get("work") or ""),
            method=str(row.get("method") or ""),
            dataset=str(row.get("dataset") or ""),
            key_result=str(row.get("key_result") or ""),
        )
        for row in (raw.get("comparison_table") or [])[:5]
        if isinstance(row, dict)
    ]

    logger.info("external_review_done", topic=topic, n_papers=len(paper_models), source=source)
    return ExternalReviewOut(
        topic=topic,
        papers=paper_models,
        synthesis=str(raw.get("synthesis") or ""),
        relevance_notes=str(raw.get("relevance_notes") or ""),
        comparison_table=comp_rows,
        gaps=[str(g).strip() for g in (raw.get("gaps") or [])[:5] if g],
        top_cite=str(raw.get("top_cite") or ""),
        source=source,
        generated_at=datetime.now(timezone.utc),
    )


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_literature_review(
    review_id: int,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    row = db.query(LiteratureReview).filter(LiteratureReview.id == review_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(row)
    db.commit()
    logger.info("literature_review_deleted", review_id=review_id)


# ── ARISE JSON export (Story 4.1) ─────────────────────────────────────────────


@router.post("/export-arise", response_model=List[AriseArticleOut])
async def export_arise(
    body: AriseExportRequest,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Export requirement-rich articles for downstream ARISE pipelines (NFR15 schema)."""
    since = body.since
    rows = (
        db.query(Article, Feed.name.label("feed_name"))
        .join(Feed, Article.feed_id == Feed.id)
        .filter(
            Article.re_document_type.in_(ARISE_RE_DOCUMENT_TYPES),
            Article.published_at.isnot(None),
            Article.published_at >= since,
        )
        .order_by(Article.id.asc())
        .all()
    )
    out: List[AriseArticleOut] = []
    for article, fname in rows:
        out.append(build_arise_row(article, fname or ""))
    logger.info("arise_export", n_rows=len(out), since=since.isoformat())
    return out


# ── Novelty Threat Monitor (Story 5.1) ────────────────────────────────────────

_LLM_TIMEOUT = 45
_THREAT_LLM_MODEL = os.getenv("QA_MODEL", os.getenv("SCORER_MODEL", "google/gemini-flash-1.5"))
_UNI_OLLAMA_URL = os.getenv("UNI_OLLAMA_URL", "").rstrip("/")
_OLLAMA_LLM_URL = os.getenv("OLLAMA_URL", "http://host-gateway:11434").rstrip("/")
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

_THREAT_SYSTEM_PROMPT = """\
You are a research novelty analyst. You compare an academic paper's contribution against a PhD researcher's stated thesis contribution and assess overlap.

Respond with valid JSON only:
{
  "overlap_score": <float 0.0–1.0>,
  "positioning_note": "<2–3 sentences: what overlaps, and crucially how the researcher's contribution remains distinct>"
}

overlap_score guide:
0.0–0.3: No meaningful overlap — different domain, method, or problem
0.3–0.6: Partial overlap — similar topic but different approach or scope
0.6–0.8: Significant overlap — same problem space, requires differentiation
0.8–1.0: Critical — paper likely covers the researcher's core contribution"""


async def _llm_assess_threat(statement: str, article: Any, db: Session) -> dict:
    """Call LLM to assess overlap between thesis contribution and an article.

    Uses the same 3-tier routing as ask.py: UNI_OLLAMA_URL → OLLAMA_URL → OPENROUTER_API_KEY.
    Returns parsed JSON with overlap_score and positioning_note.
    """
    try:
        tags = json.loads(article.tags_json or "[]")
    except Exception:
        tags = []
    summary_bullets = []
    try:
        summary_bullets = json.loads(article.summary_bullets_json or "[]")
    except Exception:
        pass

    user_prompt = (
        f"RESEARCHER'S THESIS CONTRIBUTION:\n{statement}\n\n"
        f"PAPER TO ASSESS:\n"
        f"Title: {article.title}\n"
        f"Summary: {'\n'.join(summary_bullets)}\n"
        f"Tags: {', '.join(tags)}\n"
        f"Scorer reason: {article.reason or ''}\n\n"
        "Assess overlap."
    )

    messages = [
        {"role": "system", "content": _THREAT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
        # Tier 1: UNI_OLLAMA_URL
        if _UNI_OLLAMA_URL:
            try:
                resp = await client.post(
                    f"{_UNI_OLLAMA_URL}/api/chat",
                    json={"model": _THREAT_LLM_MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.1, "num_predict": 512}},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data.get("message", {}).get("content", "")
                    return _parse_threat_json(raw)
                logger.warning("threat_uni_ollama_failed", status=resp.status_code)
            except Exception as e:
                logger.warning("threat_uni_ollama_error", error=str(e))

        # Tier 2: local OLLAMA_URL
        try:
            resp = await client.post(
                f"{_OLLAMA_LLM_URL}/api/chat",
                json={"model": _THREAT_LLM_MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.1, "num_predict": 512}},
            )
            if resp.status_code == 200:
                data = resp.json()
                raw = data.get("message", {}).get("content", "")
                return _parse_threat_json(raw)
            logger.warning("threat_ollama_failed", status=resp.status_code)
        except Exception as e:
            logger.warning("threat_ollama_error", error=str(e))

    # Tier 3: OpenRouter
    if _OPENROUTER_KEY and _OPENROUTER_KEY.startswith("sk-"):
        try:
            async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as or_client:
                resp = await or_client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {_OPENROUTER_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": _THREAT_LLM_MODEL,
                        "messages": messages,
                        "max_tokens": 512,
                        "temperature": 0.1,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"]
                    return _parse_threat_json(raw)
                logger.warning("threat_openrouter_failed", status=resp.status_code)
        except Exception as e:
            logger.warning("threat_openrouter_error", error=str(e))

    raise RuntimeError("All LLM tiers exhausted for threat assessment")


def _parse_threat_json(raw: str) -> dict:
    """Parse LLM JSON response, handling markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


async def _run_threat_scan(db: Session, window_days: int = 14) -> ThreatScanResponse:
    """Scan high-scored articles and assess novelty threat."""
    contribution = db.query(ThesisContribution).first()
    if not contribution:
        raise HTTPException(
            status_code=400,
            detail="No thesis contribution statement configured. Use PUT /api/research/profile/contribution first.",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    already_checked = {r.article_id for r in db.query(NoveltyAlert.article_id).all()}

    query = db.query(Article).filter(Article.score >= 7.0, Article.created_at >= cutoff)
    if already_checked:
        query = query.filter(Article.id.notin_(already_checked))
    candidates = query.all()

    scanned = skipped = alerts_created = 0
    for article in candidates:
        scanned += 1
        try:
            result = await _llm_assess_threat(contribution.statement, article, db)
            overlap = result.get("overlap_score", 0.0)
            note = result.get("positioning_note", "")
            db.add(NoveltyAlert(
                article_id=article.id,
                overlap_score=min(1.0, max(0.0, float(overlap))),
                positioning_note=str(note)[:1000],
                checked_at=datetime.now(timezone.utc),
            ))
            db.commit()
            alerts_created += 1
        except Exception as e:
            logger.warning("threat_scan_llm_failed", article_id=article.id, error=str(e))
            skipped += 1

    return ThreatScanResponse(scanned=scanned, alerts_created=alerts_created, skipped=skipped)


@router.get("/profile/contribution", response_model=Optional[ThesisContributionOut])
async def get_contribution(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return the current thesis contribution statement, or null if not set."""
    row = db.query(ThesisContribution).first()
    if not row:
        return None
    return ThesisContributionOut.model_validate(row)


@router.put("/profile/contribution", response_model=ThesisContributionOut)
async def put_contribution(
    body: ThesisContributionUpdate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Upsert the thesis contribution statement (singleton — only one row ever exists)."""
    now = datetime.now(timezone.utc)
    existing = db.query(ThesisContribution).first()
    if existing:
        existing.statement = body.statement
        existing.updated_at = now
    else:
        db.add(ThesisContribution(id=1, statement=body.statement, updated_at=now))
    db.commit()
    row = db.query(ThesisContribution).first()
    return ThesisContributionOut.model_validate(row)


@router.post("/threats/scan", response_model=ThreatScanResponse)
async def scan_threats(
    window_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Scan recent high-scored articles for novelty overlap with the thesis contribution.

    Returns ThreatScanResponse with counts of scanned, alerted, and skipped articles.
    Returns 400 if no thesis contribution is configured.
    """
    return await _run_threat_scan(db, window_days=window_days)


@router.get("/threats", response_model=List[NoveltyAlertOut])
async def list_threats(
    since_days: int = Query(default=30, ge=1, le=365),
    min_overlap: float = Query(default=0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return threat assessments, sorted by overlap_score descending."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    rows = (
        db.query(NoveltyAlert, Article.title, Article.url, Article.score)
        .join(Article, NoveltyAlert.article_id == Article.id)
        .filter(NoveltyAlert.checked_at >= cutoff, NoveltyAlert.overlap_score >= min_overlap)
        .order_by(NoveltyAlert.overlap_score.desc())
        .all()
    )
    return [
        NoveltyAlertOut(
            article_id=alert.article_id,
            title=article_title,
            url=article_url,
            score=article_score,
            overlap_score=alert.overlap_score,
            positioning_note=alert.positioning_note,
            checked_at=alert.checked_at,
        )
        for alert, article_title, article_url, article_score in rows
    ]


# ── Author Radar (Story 5.2) ──────────────────────────────────────────────────

import math as _math


@router.get("/authors", response_model=List[TrackedAuthorOut])
async def list_authors(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return tracked authors sorted by relevance (avg_score * log1p(paper_count))."""
    rows = db.query(TrackedAuthor).all()
    rows.sort(
        key=lambda a: a.avg_score * _math.log1p(a.paper_count),
        reverse=True,
    )
    return [TrackedAuthorOut.model_validate(r) for r in rows]


@router.post("/authors/scan", response_model=AuthorScanResponse)
async def scan_authors(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Trigger author radar scan for all tracked authors."""
    from author_radar import run_author_radar_scan  # noqa: PLC0415

    return await run_author_radar_scan(db)


@router.delete("/authors/{ss_author_id}", status_code=204)
async def delete_author(
    ss_author_id: str,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Remove an author from tracking. Existing articles keep their tracked_author_alert flag."""
    author = db.query(TrackedAuthor).filter_by(ss_author_id=ss_author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    db.delete(author)
    db.commit()
    logger.info("author_deleted", ss_author_id=ss_author_id)


# ── Highlights → Writing Pipeline (Story 5.3) ─────────────────────────────────

_LLM_SYNTHESIS_MODEL = os.getenv("QA_MODEL", os.getenv("SCORER_MODEL", "google/gemini-flash-1.5"))

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a PhD thesis writing assistant. You help draft synthesis paragraphs from reading highlights.

Write a cohesive academic synthesis paragraph of 180–250 words that:
1. Synthesizes the key findings across these passages with proper academic hedging ("X et al. show...", "Several studies suggest...")
2. Uses in-text citation placeholders like [Author Year] derived from the paper titles where possible
3. Ends with a forward-looking gap sentence that sets up the researcher's own contribution
4. Is ready to paste into the specified thesis section with minimal editing

Output only the paragraph — no preamble, no explanation."""


def _format_highlights_for_prompt(highlight_rows: list, max_chars: int = 6000) -> str:
    """Format highlights into prompt block, truncating oldest/lowest-scored first."""
    lines: list[str] = []
    for h, article, article_score in highlight_rows:
        pub_year = ""
        if article.paper_meta_json:
            try:
                pm = json.loads(article.paper_meta_json)
                if pm.get("year"):
                    pub_year = str(pm["year"])
            except Exception:
                pass
        note_line = f"Note: {h.note}" if h.note else ""
        score_str = f"{article_score:.1f}" if article_score else "N/A"
        lines.append(
            f"[Score {score_str}] {article.title} ({pub_year})\n"
            f"> \"{h.selected_text}\"\n"
            f"{note_line}\n---"
        )

    text = "\n".join(lines)
    if len(text) > max_chars:
        # Truncate: remove from the end (oldest/lowest scored highlights)
        text = text[:max_chars]
        # Try to break at last --- boundary
        last_break = text.rfind("\n---")
        if last_break > max_chars * 0.7:
            text = text[:last_break]
    return text


async def _llm_synthesize_highlights(thesis_section: str, formatted_highlights: str, article_count: int) -> AsyncGenerator[str, None]:
    """Stream LLM synthesis via SSE (same pattern as ask.py)."""
    user_prompt = (
        f"THESIS SECTION: {thesis_section}\n"
        f"RESEARCHER DOMAIN: AI-driven model-based engineering for cyber-physical systems.\n\n"
        f"HIGHLIGHTED PASSAGES (from {article_count} papers, best scored first):\n"
        f"{formatted_highlights}\n\n"
        f"Write a cohesive academic synthesis paragraph of 180–250 words for the {thesis_section} section."
    )

    messages = [
        {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # 3-tier LLM routing (same as threat scan and ask.py)
    async with httpx.AsyncClient(timeout=60) as client:
        # Tier 1: UNI_OLLAMA_URL
        if _UNI_OLLAMA_URL:
            try:
                async with client.stream(
                    "POST",
                    f"{_UNI_OLLAMA_URL}/api/chat",
                    json={"model": _LLM_SYNTHESIS_MODEL, "messages": messages, "stream": True, "options": {"temperature": 0.3, "num_predict": 1024}},
                ) as resp:
                    if resp.status_code == 200:
                        async for line in resp.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk = json.loads(line)
                                delta = chunk.get("message", {}).get("content", "")
                                if delta:
                                    yield f"data: {json.dumps({'text': delta})}\n\n"
                                if chunk.get("done"):
                                    return
                            except Exception:
                                pass
                        return
            except Exception as e:
                logger.warning("synthesis_uni_ollama_error", error=str(e))

        # Tier 2: local OLLAMA_URL
        try:
            async with client.stream(
                "POST",
                f"{_OLLAMA_LLM_URL}/api/chat",
                json={"model": _LLM_SYNTHESIS_MODEL, "messages": messages, "stream": True, "options": {"temperature": 0.3, "num_predict": 1024}},
            ) as resp:
                if resp.status_code == 200:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            delta = chunk.get("message", {}).get("content", "")
                            if delta:
                                yield f"data: {json.dumps({'text': delta})}\n\n"
                            if chunk.get("done"):
                                return
                        except Exception:
                            pass
                    return
        except Exception as e:
            logger.warning("synthesis_ollama_error", error=str(e))

    # Tier 3: OpenRouter (must reach here before yielding)
    if _OPENROUTER_KEY and _OPENROUTER_KEY.startswith("sk-"):
        try:
            async with httpx.AsyncClient(timeout=60) as or_client:
                async with or_client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {_OPENROUTER_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": _LLM_SYNTHESIS_MODEL,
                        "messages": messages,
                        "stream": True,
                        "max_tokens": 1024,
                        "temperature": 0.3,
                    },
                ) as resp:
                    if resp.status_code == 200:
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data = line[6:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = chunk["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield f"data: {json.dumps({'text': delta})}\n\n"
                            except Exception:
                                pass
        except Exception as e:
            logger.warning("synthesis_openrouter_error", error=str(e))

    yield f"data: {json.dumps({'error': 'All LLM tiers exhausted'})}\n\n"
    yield "data: {\"done\": true}\n\n"


@router.post("/export-highlights")
async def export_highlights(
    body: HighlightExportRequest,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Synthesize tagged highlights into a writing block via streaming LLM."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=body.window_days)

    # Query highlights with article join, ordered by article score desc
    results = (
        db.query(Highlight, Article, Article.score)
        .join(Article, Highlight.article_id == Article.id)
        .filter(
            Highlight.thesis_section == body.thesis_section,
            Highlight.created_at >= cutoff,
        )
        .order_by(Article.score.desc().nullslast())
        .all()
    )

    if len(results) < 2:
        raise HTTPException(
            status_code=422,
            detail=f"Not enough highlights for synthesis (found {len(results)}, minimum 2).",
        )

    # Limit to max_highlights
    results = results[: body.max_highlights]
    article_ids = list({r.article_id for r, _, _ in results})

    formatted = _format_highlights_for_prompt(results)

    async def generate():
        async for event in _llm_synthesize_highlights(body.thesis_section, formatted, len(article_ids)):
            yield event
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/export-highlights/sections")
async def list_highlight_sections(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return all thesis sections with their highlight counts (0 for untagged sections)."""
    from sqlalchemy import func

    counts_rows = (
        db.query(Highlight.thesis_section, func.count(Highlight.id).label("count"))
        .filter(Highlight.thesis_section.isnot(None))
        .group_by(Highlight.thesis_section)
        .all()
    )
    count_map = {row[0]: row[1] for row in counts_rows}
    return [
        {"thesis_section": section, "count": count_map.get(section, 0)}
        for section in sorted(_VALID_THESIS_SECTIONS)
    ]


# ── In-Corpus Citation Graph (Story 5.5) ──────────────────────────────────────


@router.post("/citations/index")
async def trigger_citation_index(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Trigger a citation index run in the background."""
    from citation_indexer import index_citations  # noqa: PLC0415

    background_tasks.add_task(index_citations, db)
    return {"status": "indexing started"}


@router.get("/citations/stats", response_model=CitationStatsOut)
async def citation_stats(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return citation graph statistics."""
    from sqlalchemy import func  # noqa: PLC0415

    # Papers with ss_paper_id
    indexed_papers = (
        db.query(func.count(Article.id))
        .filter(Article.ss_paper_id.isnot(None))
        .scalar()
    ) or 0

    # Sum of all citation links
    total_citation_links = (
        db.query(func.coalesce(func.sum(Article.cited_by_corpus_count), 0))
        .scalar()
    ) or 0

    # Top 10 most cited
    top_rows = (
        db.query(Article.id, Article.title, Article.score, Article.cited_by_corpus_count)
        .filter(Article.cited_by_corpus_count > 0)
        .order_by(Article.cited_by_corpus_count.desc())
        .limit(10)
        .all()
    )
    top_cited = [
        TopCitedItem(
            id=r.id,
            title=r.title,
            score=r.score,
            cited_by_corpus_count=r.cited_by_corpus_count,
        )
        for r in top_rows
    ]

    # Last indexed time
    raw = get_setting(db, "citations_last_indexed_at", "")
    last_indexed_at: datetime | None = None
    if raw:
        try:
            last_indexed_at = datetime.fromisoformat(raw)
        except Exception:
            pass

    return CitationStatsOut(
        indexed_papers=indexed_papers,
        total_citation_links=total_citation_links,
        top_cited=top_cited,
        last_indexed_at=last_indexed_at,
    )


# ── Conference Radar (Story 5.6) ──────────────────────────────────────────────


@router.get("/conferences", response_model=List[ConferenceOut])
async def list_conferences(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return all conferences with countdowns and bookmark state."""
    from conferences import get_conferences_with_countdown  # noqa: PLC0415

    raw = get_setting(db, "bookmarked_conferences", "")
    bookmarked = set(v.strip() for v in raw.split(",") if v.strip())
    return get_conferences_with_countdown(bookmarked)


@router.post("/conferences/bookmark", response_model=List[ConferenceOut])
async def toggle_conference_bookmark(
    body: ConferenceBookmark,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Toggle bookmark for a conference venue."""
    from conferences import get_conferences_with_countdown  # noqa: PLC0415

    raw = get_setting(db, "bookmarked_conferences", "")
    bookmarked = set(v.strip() for v in raw.split(",") if v.strip())

    if body.bookmarked:
        bookmarked.add(body.venue)
    else:
        bookmarked.discard(body.venue)

    set_setting(db, "bookmarked_conferences", ",".join(sorted(bookmarked)))
    return get_conferences_with_countdown(bookmarked)
