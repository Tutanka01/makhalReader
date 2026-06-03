"""Author Radar scanner (Story 5.2).

Periodically checks tracked authors for new publications via Semantic Scholar
and queues them for ingestion through the internal article creation endpoint.
"""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog
from sqlalchemy.orm import Session

from database import Article, TrackedAuthor, get_db
from models import AuthorScanResponse

logger = structlog.get_logger().bind(service="author_radar")

SS_API_BASE = "https://api.semanticscholar.org/graph/v1"
SS_API_KEY = os.getenv("SS_API_KEY", "").strip()
INTERNAL_API_BASE = os.getenv("INTERNAL_API_BASE", "http://api:8000")
API_SECRET = os.getenv("API_SECRET", "changeme")

_arxiv_re = re.compile(r"arxiv\.org/abs/(\d+\.\d+)")
_ss_headers: dict[str, str] = {}
if SS_API_KEY:
    _ss_headers["x-api-key"] = SS_API_KEY


def _extract_arxiv_id(url: str) -> Optional[str]:
    """Extract arXiv ID from a URL, e.g. https://arxiv.org/abs/2401.12345 -> 2401.12345."""
    m = _arxiv_re.search(url)
    return m.group(1) if m else None


async def _fetch_author_papers(
    client: httpx.AsyncClient, ss_author_id: str, cutoff_date: str
) -> list[dict]:
    """Fetch recent papers for a SS author. Returns list of paper dicts."""
    url = f"{SS_API_BASE}/author/{ss_author_id}/papers"
    params = {"fields": "title,externalIds,year,publicationDate", "limit": 10}
    try:
        resp = await client.get(url, params=params, headers=_ss_headers, timeout=30)
        if resp.status_code == 429:
            logger.warning("author_scan_rate_limited", ss_author_id=ss_author_id)
            await asyncio.sleep(5)
            resp = await client.get(url, params=params, headers=_ss_headers, timeout=30)
        if resp.status_code != 200:
            logger.warning("author_scan_ss_failed", ss_author_id=ss_author_id, status=resp.status_code)
            return []
        data = resp.json()
        papers = data.get("data", [])
        # Filter to papers published within last 90 days
        recent: list[dict] = []
        for p in papers:
            pub_date = p.get("publicationDate") or ""
            if pub_date and pub_date >= cutoff_date:
                recent.append(p)
        return recent
    except Exception as e:
        logger.warning("author_scan_error", ss_author_id=ss_author_id, error=str(e))
        return []


async def _paper_exists_in_db(db: Session, paper: dict) -> bool:
    """Check if a paper already exists in our DB by arXiv ID or DOI."""
    ext_ids = paper.get("externalIds") or {}
    arxiv_id = ext_ids.get("ArXiv")
    doi = ext_ids.get("DOI")

    if arxiv_id:
        expected_url = f"https://arxiv.org/abs/{arxiv_id}"
        exists = db.query(Article.id).filter(Article.url == expected_url).first()
        if exists:
            return True

    if doi:
        doi_url = f"https://doi.org/{doi}"
        exists = db.query(Article.id).filter(Article.url == doi_url).first()
        if exists:
            return True
        # Also check if DOI appears in paper_meta_json
        rows = (
            db.query(Article.id)
            .filter(Article.paper_meta_json.isnot(None))
            .all()
        )
        for row in rows:
            try:
                meta = row[0].paper_meta_json if hasattr(row[0], 'paper_meta_json') else None
            except Exception:
                continue  # row is a tuple (id,)
        # Simpler: iterate and check paper_meta
        for row in db.query(Article).filter(Article.paper_meta_json.isnot(None)).all():
            try:
                pm = json.loads(row.paper_meta_json)
                if pm.get("doi") == doi or pm.get("paperId") == paper.get("paperId"):
                    return True
            except Exception:
                continue

    return False


async def _queue_article_ingestion(arxiv_id: str, tracked_author_id: int) -> bool:
    """Call the internal API to create and score a new paper article."""
    url = f"https://arxiv.org/abs/{arxiv_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            payload = {
                "feed_id": 1,
                "title": f"Author Radar: {arxiv_id}",
                "url": url,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "tracked_author_alert": True,
            }
            resp = await client.post(
                f"{INTERNAL_API_BASE}/api/internal/articles",
                json=payload,
                headers={"x-internal-secret": API_SECRET},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("created"):
                    logger.info("author_radar_article_created", arxiv_id=arxiv_id, article_id=data["id"])
                    return True
                else:
                    logger.info("author_radar_article_exists", arxiv_id=arxiv_id, existing_id=data["id"])
                    return True  # Already exists — still counts as success
            else:
                logger.warning("author_radar_ingestion_failed", arxiv_id=arxiv_id, status=resp.status_code)
                return False
        except Exception as e:
            logger.warning("author_radar_ingestion_error", arxiv_id=arxiv_id, error=str(e))
            return False


async def scan_author(db: Session, ss_author_id: str, name: str, user_id: int = 1) -> int:
    """Check one author for new papers. Returns count of new articles queued."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=30) as client:
        papers = await _fetch_author_papers(client, ss_author_id, cutoff)

    new_count = 0
    for paper in papers:
        ext_ids = paper.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv")
        if not arxiv_id:
            continue
        if await _paper_exists_in_db(db, paper):
            continue
        if await _queue_article_ingestion(arxiv_id, ss_author_id):
            new_count += 1

    # Update last_checked and alert_count (scoped to user)
    author = db.query(TrackedAuthor).filter_by(ss_author_id=ss_author_id, user_id=user_id).first()
    if author:
        author.last_checked = datetime.now(timezone.utc)
        author.alert_count = (author.alert_count or 0) + new_count
        db.commit()

    return new_count


async def run_author_radar_scan(db: Session, user_id: int = 1) -> AuthorScanResponse:
    """Iterate tracked authors (scoped to user_id) and scan for new papers."""
    authors = db.query(TrackedAuthor).filter_by(user_id=user_id).all()
    authors_checked = 0
    new_articles_queued = 0
    skipped = 0

    for i, author in enumerate(authors):
        authors_checked += 1
        try:
            n = await scan_author(db, author.ss_author_id, author.name, user_id=author.user_id)
            new_articles_queued += n
        except Exception as e:
            logger.warning("author_scan_failed", ss_author_id=author.ss_author_id, error=str(e))
            skipped += 1

        # Rate limit: 1 req/sec (SS free tier)
        if i < len(authors) - 1:
            await asyncio.sleep(1)

    return AuthorScanResponse(
        authors_checked=authors_checked,
        new_articles_queued=new_articles_queued,
        skipped=skipped,
    )
