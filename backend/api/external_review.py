"""External academic literature search via Semantic Scholar (primary) + OpenAlex (fallback).

Rate limits:
  Semantic Scholar: 1 req/s unauthenticated · 10 req/s with SS_API_KEY env var
  OpenAlex: no auth required, polite-pool access via mailto param
"""
import os
from datetime import date
from typing import List, Optional

import httpx
import structlog

logger = structlog.get_logger().bind(service="external_review")

SS_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,authors,year,citationCount,venue,openAccessPdf,externalIds"

OA_SEARCH_URL = "https://api.openalex.org/works"
OA_EMAIL = os.getenv("OA_CONTACT_EMAIL", "basira@research.local")

SS_API_KEY = os.getenv("SS_API_KEY", "").strip()


def _reconstruct_abstract(inv: Optional[dict]) -> str:
    """OpenAlex stores abstracts as inverted index {word: [positions]}."""
    if not inv:
        return ""
    positions: dict[int, str] = {}
    for word, pos_list in inv.items():
        for pos in pos_list:
            positions[pos] = word
    return " ".join(positions[k] for k in sorted(positions))


async def search_semantic_scholar(
    query: str,
    limit: int = 30,
    min_year: int = 2018,
) -> List[dict]:
    """Return up to `limit` papers from Semantic Scholar matching `query`."""
    headers: dict = {"Accept": "application/json"}
    if SS_API_KEY:
        headers["x-api-key"] = SS_API_KEY

    params = {
        "query": query,
        "fields": SS_FIELDS,
        "limit": min(limit + 10, 100),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(SS_SEARCH_URL, params=params, headers=headers)
            if not resp.is_success:
                logger.warning("ss_search_http_error", status=resp.status_code, body=resp.text[:200])
                return []
            raw = resp.json()
        except Exception as e:
            logger.warning("ss_search_exception", error=str(e))
            return []

    papers: List[dict] = []
    for i, p in enumerate(raw.get("data", [])):
        year = p.get("year") or 0
        if year and year < min_year:
            continue
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI", "")
        pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
        ss_id = p.get("paperId") or ""
        url = pdf_url or (f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{ss_id}")
        papers.append({
            "title": (p.get("title") or "").strip(),
            "abstract": (p.get("abstract") or "").strip(),
            "authors": [a.get("name", "") for a in (p.get("authors") or [])[:6]],
            "year": year,
            "citation_count": p.get("citationCount") or 0,
            "venue": (p.get("venue") or "").strip(),
            "url": url,
            "source": "semantic_scholar",
            "_position": i,
        })

    logger.info("ss_search_done", query=query, n=len(papers))
    return papers[:limit]


async def search_openalex(
    query: str,
    limit: int = 30,
    min_year: int = 2018,
) -> List[dict]:
    """Return up to `limit` papers from OpenAlex matching `query`."""
    params = {
        "search": query,
        "filter": f"from_publication_date:{min_year}-01-01,type:article",
        "sort": "relevance_score:desc",
        "per-page": min(limit + 10, 200),
        "select": (
            "id,title,abstract_inverted_index,authorships,"
            "publication_year,cited_by_count,primary_location,doi"
        ),
        "mailto": OA_EMAIL,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(OA_SEARCH_URL, params=params)
            if not resp.is_success:
                logger.warning("openalex_search_http_error", status=resp.status_code)
                return []
            raw = resp.json()
        except Exception as e:
            logger.warning("openalex_search_exception", error=str(e))
            return []

    papers: List[dict] = []
    for i, w in enumerate(raw.get("results", [])):
        abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])[:6]
        ]
        loc = w.get("primary_location") or {}
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        landing = loc.get("landing_page_url") or ""
        url = landing or (f"https://doi.org/{doi}" if doi else w.get("id", ""))
        venue = ((loc.get("source") or {}).get("display_name") or "").strip()
        papers.append({
            "title": (w.get("title") or "").strip(),
            "abstract": abstract.strip(),
            "authors": [a for a in authors if a],
            "year": w.get("publication_year") or 0,
            "citation_count": w.get("cited_by_count") or 0,
            "venue": venue,
            "url": url,
            "source": "openalex",
            "_position": i,
        })

    logger.info("openalex_search_done", query=query, n=len(papers))
    return papers[:limit]


def rerank_papers(papers: List[dict], current_year: Optional[int] = None) -> List[dict]:
    """Score papers by search relevance (40%), citation weight (35%), recency (25%).

    Removes papers with empty titles before ranking.
    """
    if current_year is None:
        current_year = date.today().year

    papers = [p for p in papers if (p.get("title") or "").strip()]
    if not papers:
        return []

    max_cit = max((p.get("citation_count") or 0) for p in papers) or 1
    total = len(papers)

    for p in papers:
        cit_norm = (p.get("citation_count") or 0) / max_cit
        year = p.get("year") or 2018
        recency = max(0.0, min(1.0, (year - 2015) / max(1, current_year - 2015)))
        pos = 1.0 - ((p.get("_position") or 0) / max(1, total - 1))
        p["relevance_score"] = round(0.40 * pos + 0.35 * cit_norm + 0.25 * recency, 3)

    return sorted(papers, key=lambda p: -p["relevance_score"])
