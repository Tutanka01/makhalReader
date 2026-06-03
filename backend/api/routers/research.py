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
from fastapi.responses import Response, StreamingResponse

from database import (
    Article,
    Feed,
    Highlight,
    LiteratureReview,
    NoveltyAlert,
    ResearchProfile,
    ThesisContribution,
    TrackedAuthor,
    UserConfig,
    get_db,
    get_setting,
    get_user_setting,
    get_valid_thesis_sections,
    set_setting,
    set_user_setting,
)
from conferences import get_conferences_with_countdown
from models import (
    AriseArticleOut,
    AriseExportRequest,
    AuthorScanResponse,
    BulkUpdateHighlightsRequest,
    CitationIndexResult,
    CitationStatsOut,
    ClusterOut,
    ComparisonRow,
    ConferenceBookmark,
    ConferenceOut,
    DismissNotificationsRequest,
    ExternalPaper,
    ExternalReviewCreate,
    ExternalReviewOut,
    HighlightExportOut,
    HighlightExportRequest,
    HighlightOut,
    LiteratureReviewCreate,
    LiteratureReviewOut,
    LiteratureReviewSummaryOut,
    MultiSectionExportRequest,
    NotificationCounts,
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
    current_user: dict = Depends(require_session),
):
    """Return HDBSCAN cluster summaries for embedded articles in the last window_days.

    Returns [] (not an error) when:
    - Fewer than min_size articles are embedded in the window
    - All articles are classified as noise by HDBSCAN
    - ChromaDB is unavailable
    - Any other exception (logged as warning)
    """
    user_id = current_user["id"]
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

        collection = _get_chroma(user_id)
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
        from sklearn.cluster import AgglomerativeClustering  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        vectors = [id_to_vector[a.id] for a in valid_articles]
        matrix = np.array(vectors, dtype=np.float32)

        labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=0.4,
            metric='cosine',
            linkage='average'
        ).fit_predict(matrix)

        clusters: List[ClusterOut] = []
        for cluster_id in sorted(set(labels)):
            if cluster_id == -1:  # noise (Agglomerative doesn't typically output -1, but just in case)
                continue

            mask = labels == cluster_id
            cluster_articles = [a for a, m in zip(valid_articles, mask) if m]
            if len(cluster_articles) < min_size:
                continue
                
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
                cluster_id=int(cluster_id),
                size=len(cluster_articles),
                centroid_title=centroid_title,
                top_tags=top_tags,
                article_ids=[a.id for a in cluster_articles],
                article_titles=[a.title for a in cluster_articles],
            ))

        # Sort clusters by size descending
        clusters.sort(key=lambda c: c.size, reverse=True)

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
    current_user: dict = Depends(require_session),
):
    """Return all researcher profile entries for the current user."""
    rows = (
        db.query(ResearchProfile)
        .filter(ResearchProfile.user_id == current_user["id"])
        .order_by(ResearchProfile.kind, ResearchProfile.weight.desc())
        .all()
    )
    return [_profile_to_entry(r) for r in rows]


@router.put("/profile", response_model=List[ResearchProfileEntry])
async def put_profile(
    payload: ResearchProfileUpsert,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Upsert profile entries scoped to the current user. weight==0 deletes."""
    user_id = current_user["id"]
    for entry in payload.entries:
        norm_label = entry.label.strip().lower()
        if not norm_label:
            continue

        existing = (
            db.query(ResearchProfile)
            .filter(
                ResearchProfile.user_id == user_id,
                ResearchProfile.kind == entry.kind,
                ResearchProfile.label == norm_label,
            )
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
                    user_id=user_id,
                    kind=entry.kind,
                    label=norm_label,
                    weight=entry.weight,
                    source=entry.source,
                ))

    db.commit()
    rows = (
        db.query(ResearchProfile)
        .filter(ResearchProfile.user_id == user_id)
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
    current_user: dict = Depends(require_session),
):
    """Embed topic → Chroma top-50 → rigor/window filter → HDBSCAN → per-cluster LLM → persist."""
    user_id = current_user["id"]
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

        collection = _get_chroma(user_id)
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

        collection = _get_chroma(user_id)
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
        user_id=current_user["id"],
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
        user_id=row.user_id,
        topic=row.topic,
        window_days=row.window_days,
        min_rigor=row.min_rigor,
        clusters=cluster_payloads,
        created_at=row.created_at,
    )


@router.get("/reviews", response_model=List[LiteratureReviewSummaryOut])
async def list_literature_reviews(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    rows = (
        db.query(LiteratureReview)
        .filter(LiteratureReview.user_id == current_user["id"])
        .order_by(LiteratureReview.created_at.desc())
        .all()
    )
    return [
        LiteratureReviewSummaryOut(
            id=r.id,
            user_id=r.user_id,
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
    current_user: dict = Depends(require_session),
):
    row = (
        db.query(LiteratureReview)
        .filter(LiteratureReview.id == review_id, LiteratureReview.user_id == current_user["id"])
        .first()
    )
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
        user_id=row.user_id,
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
    current_user: dict = Depends(require_session),
):
    row = (
        db.query(LiteratureReview)
        .filter(LiteratureReview.id == review_id, LiteratureReview.user_id == current_user["id"])
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(row)
    db.commit()
    logger.info("literature_review_deleted", review_id=review_id)


@router.get("/reviews/{review_id}/export")
async def export_literature_review(
    review_id: int,
    format: str = Query(default="md", pattern=r"^(md|docx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Export a literature review as Markdown, DOCX, or PDF."""
    row = (
        db.query(LiteratureReview)
        .filter(LiteratureReview.id == review_id, LiteratureReview.user_id == current_user["id"])
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")

    clusters = json.loads(row.body_json) if row.body_json else []
    review_data = {
        "topic": row.topic,
        "window_days": row.window_days,
        "min_rigor": row.min_rigor,
        "created_at": row.created_at.isoformat(),
        "clusters": clusters,
    }

    if format == "md":
        from litreview_exporter import review_to_markdown  # noqa: PLC0415

        content = review_to_markdown(review_data)
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="review-{review_id}.md"'},
        )

    if format == "docx":
        from litreview_exporter import export_review_docx  # noqa: PLC0415

        buf = export_review_docx(review_data)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="review-{review_id}.docx"'},
        )

    if format == "pdf":
        from litreview_exporter import export_review_pdf  # noqa: PLC0415

        buf = export_review_pdf(review_data)
        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="review-{review_id}.pdf"'},
        )


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

    summary_text = '\n'.join(summary_bullets)
    user_prompt = (
        f"RESEARCHER'S THESIS CONTRIBUTION:\n{statement}\n\n"
        f"PAPER TO ASSESS:\n"
        f"Title: {article.title}\n"
        f"Summary: {summary_text}\n"
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


async def _run_threat_scan(db: Session, user_id: int = 1, window_days: int = 14) -> ThreatScanResponse:
    """Scan high-scored articles and assess novelty threat for a given user."""
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    contribution = config.thesis_contribution if config and config.thesis_contribution else None
    if not contribution:
        raise HTTPException(
            status_code=400,
            detail="No thesis contribution statement configured. Use PUT /api/profile/config to set it.",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    already_checked = {
        r.article_id
        for r in db.query(NoveltyAlert.article_id)
        .filter(NoveltyAlert.user_id == user_id)
        .all()
    }

    query = db.query(Article).filter(Article.score >= 7.0, Article.created_at >= cutoff)
    if already_checked:
        query = query.filter(Article.id.notin_(already_checked))
    candidates = query.all()

    scanned = skipped = alerts_created = 0
    for article in candidates:
        scanned += 1
        try:
            result = await _llm_assess_threat(str(contribution), article, db)
            overlap = result.get("overlap_score", 0.0)
            note = result.get("positioning_note", "")
            db.add(NoveltyAlert(
                article_id=article.id,
                user_id=user_id,
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
    current_user: dict = Depends(require_session),
):
    """Scan recent high-scored articles for novelty overlap with the thesis contribution.

    Returns ThreatScanResponse with counts of scanned, alerted, and skipped articles.
    Returns 400 if no thesis contribution is configured.
    """
    return await _run_threat_scan(db, user_id=current_user["id"], window_days=window_days)


@router.get("/threats", response_model=List[NoveltyAlertOut])
async def list_threats(
    since_days: int = Query(default=30, ge=1, le=365),
    min_overlap: float = Query(default=0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Return threat assessments for the current user, sorted by overlap_score descending."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    rows = (
        db.query(NoveltyAlert, Article.title, Article.url, Article.score)
        .join(Article, NoveltyAlert.article_id == Article.id)
        .filter(
            NoveltyAlert.user_id == current_user["id"],
            NoveltyAlert.checked_at >= cutoff,
            NoveltyAlert.overlap_score >= min_overlap,
        )
        .order_by(NoveltyAlert.overlap_score.desc())
        .all()
    )
    return [
        NoveltyAlertOut(
            article_id=alert.article_id,
            user_id=alert.user_id,
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
    current_user: dict = Depends(require_session),
):
    """Return tracked authors sorted by relevance (avg_score * log1p(paper_count))."""
    user_id = current_user["id"]
    rows = db.query(TrackedAuthor).filter_by(user_id=user_id).all()
    rows.sort(
        key=lambda a: a.avg_score * _math.log1p(a.paper_count),
        reverse=True,
    )
    return [TrackedAuthorOut.model_validate(r) for r in rows]


@router.post("/authors/scan", response_model=AuthorScanResponse)
async def scan_authors(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Trigger author radar scan for current user's tracked authors."""
    from author_radar import run_author_radar_scan  # noqa: PLC0415

    return await run_author_radar_scan(db, user_id=current_user["id"])


@router.delete("/authors/{ss_author_id}", status_code=204)
async def delete_author(
    ss_author_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Remove an author from tracking. Existing articles keep their tracked_author_alert flag."""
    user_id = current_user["id"]
    author = db.query(TrackedAuthor).filter_by(ss_author_id=ss_author_id, user_id=user_id).first()
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
    current_user: dict = Depends(require_session),
):
    """Synthesize tagged highlights into a writing block via streaming LLM."""
    valid = get_valid_thesis_sections(db, current_user["id"])
    if body.thesis_section not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"thesis_section must be one of {sorted(valid)}",
        )
    cutoff = datetime.now(timezone.utc) - timedelta(days=body.window_days)

    # Query highlights with article join, ordered by article score desc
    results = (
        db.query(Highlight, Article, Article.score)
        .join(Article, Highlight.article_id == Article.id)
        .filter(
            Highlight.thesis_section == body.thesis_section,
            Highlight.created_at >= cutoff,
            Highlight.user_id == current_user["id"],
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
    current_user: dict = Depends(require_session),
):
    """Return the current user's thesis sections with highlight counts."""
    from sqlalchemy import func

    valid_sections = get_valid_thesis_sections(db, current_user["id"])
    counts_rows = (
        db.query(Highlight.thesis_section, func.count(Highlight.id).label("count"))
        .filter(
            Highlight.thesis_section.isnot(None),
            Highlight.user_id == current_user["id"],
        )
        .group_by(Highlight.thesis_section)
        .all()
    )
    count_map = {row[0]: row[1] for row in counts_rows}
    return [
        {"thesis_section": section, "count": count_map.get(section, 0)}
        for section in sorted(valid_sections)
    ]


async def _synthesize_section_text(thesis_section: str, db: Session, user_id: int = 1, window_days: int = 90, max_highlights: int = 30) -> str:
    """Run synthesis for a section and return the plain text result."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    results = (
        db.query(Highlight, Article, Article.score)
        .join(Article, Highlight.article_id == Article.id)
        .filter(
            Highlight.thesis_section == thesis_section,
            Highlight.created_at >= cutoff,
            Highlight.user_id == user_id,
        )
        .order_by(Article.score.desc().nullslast())
        .all()
    )

    if len(results) < 2:
        return f"*Insufficient highlights for {thesis_section} (found {len(results)}, minimum 2).*"

    results = results[:max_highlights]
    article_ids = list({r.article_id for r, _, _ in results})
    formatted = _format_highlights_for_prompt(results)

    text_parts: list[str] = []
    async for event in _llm_synthesize_highlights(thesis_section, formatted, len(article_ids)):
        if event.startswith("data: "):
            payload = event[6:].strip()
            if payload == '{"done": true}':
                break
            try:
                parsed = json.loads(payload)
                if parsed.get("text"):
                    text_parts.append(parsed["text"])
                if parsed.get("error"):
                    text_parts.append(f"\n\n[Error: {parsed['error']}]")
            except json.JSONDecodeError:
                pass

    return "".join(text_parts)


@router.post("/export-highlights/multi")
async def export_highlights_multi(
    body: MultiSectionExportRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Export multiple thesis sections as a single Markdown or LaTeX document."""
    parts: list[str] = []
    user_id = current_user["id"]

    if body.format == "markdown":
        for section in body.sections:
            text = await _synthesize_section_text(section, db, user_id=user_id, window_days=body.window_days, max_highlights=body.max_highlights_per_section)
            parts.append(f"## {section}\n\n{text}\n")
        content = "\n".join(parts)
        media_type = "text/markdown"
        filename = "writing-export.md"
    else:
        for section in body.sections:
            text = await _synthesize_section_text(section, db, user_id=user_id, window_days=body.window_days, max_highlights=body.max_highlights_per_section)
            safe = section.replace("&", "\\&").replace("%", "\\%")
            parts.append(f"\\section{{{safe}}}\n\n{text}\n")
        content = "\\documentclass{article}\n\\begin{document}\n" + "\n".join(parts) + "\n\\end{document}"
        media_type = "text/plain"
        filename = "writing-export.tex"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/highlights/all", response_model=List[dict])
async def list_all_highlights(
    thesis_section: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """List all highlights with article info, optionally filtered by thesis_section."""
    if thesis_section:
        valid = get_valid_thesis_sections(db, current_user["id"])
        if thesis_section not in valid:
            raise HTTPException(
                status_code=422,
                detail=f"thesis_section must be one of {sorted(valid)}",
            )
    q = (
        db.query(Highlight, Article.title, Article.url, Article.score)
        .join(Article, Highlight.article_id == Article.id)
    )
    if thesis_section:
        q = q.filter(Highlight.thesis_section == thesis_section)
    rows = q.order_by(Highlight.created_at.desc()).all()

    return [
        {
            "id": h.id,
            "article_id": h.article_id,
            "selected_text": h.selected_text,
            "prefix_context": h.prefix_context,
            "suffix_context": h.suffix_context,
            "color": h.color,
            "note": h.note,
            "thesis_section": h.thesis_section,
            "created_at": h.created_at.isoformat(),
            "article_title": title,
            "article_url": url,
            "article_score": score,
        }
        for h, title, url, score in rows
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
    current_user: dict = Depends(require_session),
):
    """Return all conferences with countdowns and bookmark state."""
    from conferences import get_conferences_with_countdown  # noqa: PLC0415

    user_id = current_user["id"]
    raw = get_user_setting(db, user_id, "bookmarked_conferences", "")
    bookmarked = set(v.strip() for v in raw.split(",") if v.strip())
    return get_conferences_with_countdown(bookmarked)


@router.post("/conferences/bookmark", response_model=List[ConferenceOut])
async def toggle_conference_bookmark(
    body: ConferenceBookmark,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Toggle bookmark for a conference venue."""
    from conferences import get_conferences_with_countdown  # noqa: PLC0415

    user_id = current_user["id"]
    raw = get_user_setting(db, user_id, "bookmarked_conferences", "")
    bookmarked = set(v.strip() for v in raw.split(",") if v.strip())

    if body.bookmarked:
        bookmarked.add(body.venue)
    else:
        bookmarked.discard(body.venue)

    set_user_setting(db, user_id, "bookmarked_conferences", ",".join(sorted(bookmarked)))
    return get_conferences_with_countdown(bookmarked)


# ── Notification Badges (Story 6.2) ────────────────────────────────────────────


_NOTIFICATION_KEY_MAP = {
    "threats": "notifications_last_dismissed_threats",
    "conferences": "notifications_last_dismissed_conferences",
    "authors": "notifications_last_dismissed_authors",
}


@router.get("/notifications", response_model=NotificationCounts)
async def get_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Return counts for notification badges in the sidebar."""
    user_id = current_user["id"]

    # Threat alerts since last dismissal
    dismissed_threats = get_user_setting(db, user_id, "notifications_last_dismissed_threats", "")
    threat_cutoff = datetime.fromisoformat(dismissed_threats) if dismissed_threats else datetime.min.replace(tzinfo=timezone.utc)
    new_threats = (
        db.query(NoveltyAlert)
        .filter(
            NoveltyAlert.user_id == current_user["id"],
            NoveltyAlert.checked_at > threat_cutoff,
        )
        .count()
    )

    # Urgent conference deadlines (days_to_paper <= 14, not past)
    dismissed_confs = get_user_setting(db, user_id, "notifications_last_dismissed_conferences", "")
    conf_cutoff = datetime.fromisoformat(dismissed_confs) if dismissed_confs else datetime.min.replace(tzinfo=timezone.utc)
    all_confs = get_conferences_with_countdown()
    urgent_deadlines = sum(
        1 for c in all_confs
        if not c["is_past"] and c["days_to_paper"] <= 14
    )

    # Author papers since last dismissal
    dismissed_authors = get_user_setting(db, user_id, "notifications_last_dismissed_authors", "")
    author_cutoff = datetime.fromisoformat(dismissed_authors) if dismissed_authors else datetime.min.replace(tzinfo=timezone.utc)
    new_author_papers = (
        db.query(Article)
        .filter(
            Article.tracked_author_alert.is_(True),
            Article.created_at > author_cutoff,
        )
        .count()
    )

    return NotificationCounts(
        new_threats=new_threats,
        urgent_deadlines=urgent_deadlines,
        new_author_papers=new_author_papers,
    )


@router.post("/notifications/dismiss")
async def dismiss_notifications(
    body: DismissNotificationsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Mark a notification category as seen so its badge goes to zero."""
    user_id = current_user["id"]
    key = _NOTIFICATION_KEY_MAP[body.type]
    set_user_setting(db, user_id, key, datetime.now(timezone.utc).isoformat())
    return {"status": "ok"}


# ── BibTeX Bibliography Export (Story 7.1) ─────────────────────────────────────


@router.get("/bibliography")
async def export_bibliography(
    since_days: int = Query(default=365, ge=1, le=3650),
    min_score: Optional[float] = Query(default=None, ge=0, le=10),
    contribution_type: Optional[str] = Query(default=None, max_length=32),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Export a BibTeX bibliography from the article corpus."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    q = db.query(Article).filter(Article.created_at >= cutoff)

    if min_score is not None:
        q = q.filter(Article.score >= min_score)
    if contribution_type:
        q = q.filter(Article.contribution_type == contribution_type)

    articles = q.order_by(Article.created_at.desc()).all()

    from bibliography import generate_bibtex  # noqa: PLC0415

    content = generate_bibtex(articles)

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bibliography.bib"'},
    )
