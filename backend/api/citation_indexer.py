"""
In-Corpus Citation Graph indexer for Baṣīra.

For each article with ss_paper_id, fetches references from Semantic Scholar API,
cross-references against the corpus, and increments cited_by_corpus_count.

Reset-and-recompute pattern: starts fresh each run to avoid accumulation drift.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from database import Article, set_setting

SS_API_BASE = "https://api.semanticscholar.org/graph/v1"
SS_API_KEY = os.getenv("SS_API_KEY", "")
_RATE_LIMIT_DELAY = 1.0  # seconds between requests
_RETRY_DELAY = 5.0
_MAX_RETRIES = 1


async def index_citations(db: Session) -> dict:
    """Run a full citation index cycle. Reset-and-recompute pattern."""
    start = datetime.now(timezone.utc)

    # Step 1: reset all counts
    db.query(Article).filter(Article.ss_paper_id.isnot(None)).update(
        {Article.cited_by_corpus_count: 0}, synchronize_session=False
    )
    db.commit()

    # Step 2: build corpus paperId → article_id map
    rows = (
        db.query(Article.ss_paper_id, Article.id, Article.score)
        .filter(Article.ss_paper_id.isnot(None))
        .all()
    )
    corpus_map: dict[str, int] = {row.ss_paper_id: row.id for row in rows}
    paper_ids = list(corpus_map.keys())

    total_links = 0

    if not paper_ids:
        result = {
            "indexed_papers": 0,
            "total_citation_links": 0,
            "last_indexed_at": start,
        }
        set_setting(db, "citations_last_indexed_at", start.isoformat())
        return result

    headers = {"User-Agent": "Basira/1.0"}
    if SS_API_KEY:
        headers["x-api-key"] = SS_API_KEY

    async with httpx.AsyncClient(timeout=30) as client:
        for pid in paper_ids:
            # Rate limit
            await asyncio.sleep(_RATE_LIMIT_DELAY)

            refs = await _fetch_references(client, headers, pid)
            if refs is None:
                continue  # skipped after retries

            for ref_paper_id in refs:
                if ref_paper_id in corpus_map:
                    target_id = corpus_map[ref_paper_id]
                    db.query(Article).filter(Article.id == target_id).update(
                        {Article.cited_by_corpus_count: Article.cited_by_corpus_count + 1},
                        synchronize_session=False,
                    )
                    total_links += 1

            db.commit()

    set_setting(db, "citations_last_indexed_at", start.isoformat())

    return {
        "indexed_papers": len(paper_ids),
        "total_citation_links": total_links,
        "last_indexed_at": start,
    }


async def _fetch_references(
    client: httpx.AsyncClient, headers: dict, paper_id: str
) -> list[str] | None:
    """Fetch references for a paper, retrying once on 429."""
    url = f"{SS_API_BASE}/paper/{paper_id}/references?fields=paperId&limit=100"

    for attempt in range(1 + _MAX_RETRIES):
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 429:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                return None
            resp.raise_for_status()
            data = resp.json()
            refs: list[str] = [
                ref["citedPaper"]["paperId"]
                for ref in data.get("data", [])
                if ref.get("citedPaper") and ref["citedPaper"].get("paperId")
            ]
            return refs
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY)
                continue
            return None
        except Exception:
            return None

    return None
