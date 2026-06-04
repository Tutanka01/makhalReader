from __future__ import annotations

from typing import Optional

import httpx

from .base import FetchedArticle, ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

ARXIV_API_BASE = "http://export.arxiv.org/api/query"

ARXIV_CATEGORY_MAP: dict[str, list[str]] = {
    "physics": ["physics.gen-ph", "cond-mat.mes-hall", "astro-ph.GA", "hep-th", "nucl-th"],
    "biology": ["q-bio.BM", "q-bio.NC", "q-bio.PE", "q-bio.GN", "q-bio.QM"],
    "mathematics": ["math.AG", "math.CO", "math.ST", "math.NA", "math.GR"],
    "economics": ["econ.GN", "econ.TH", "econ.EM"],
    "statistics": ["stat.ML", "stat.TH", "stat.AP", "stat.ME"],
    "computer_science": ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.IR"],
    "electrical_engineering": ["eess.AS", "eess.IV", "eess.SP"],
    "quantum": ["quant-ph"],
}


class ArxivProvider(SourceProvider):
    provider_id = "arxiv"

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient()

    async def resolve(self, intent: SourceIntent) -> list[ResolvedSource]:
        query = intent.query.strip().lower()
        if not query:
            return []

        matched_categories: list[str] = []
        for keyword, cats in ARXIV_CATEGORY_MAP.items():
            if keyword in query or any(k in query for k in keyword.split("_")):
                matched_categories.extend(cats)

        if not matched_categories:
            matched_categories = ["cs.AI", "cs.LG", "stat.ML"]

        seen: set[str] = set()
        results: list[ResolvedSource] = []
        for cat in matched_categories:
            if cat in seen:
                continue
            seen.add(cat)
            results.append(ResolvedSource(
                name=f"arXiv {cat}",
                provider="arxiv",
                query_json={"search_query": f"cat:{cat}", "max_results": "50", "sortBy": "submittedDate"},
                label="arxiv_category",
                provenance_url=f"https://arxiv.org/list/{cat}/recent",
                category="preprint",
            ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        sq = source.query_json.get("search_query", "")
        if not sq:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        try:
            resp = await client.get(
                ARXIV_API_BASE,
                params={"search_query": sq, "max_results": "1"},
                timeout=15,
            )
        except Exception:
            return VerifiedSource(verified=False)

        if resp.status_code != 200:
            return VerifiedSource(verified=False)

        body = resp.text
        if "totalResults" in body:
            import xml.etree.ElementTree as ET
            try:
                ns = {"atom": "http://www.w3.org/2005/Atom", "opensearch": "http://a9.com/-/spec/opensearch/1.1/"}
                root = ET.fromstring(body)
                total_el = root.find(".//opensearch:totalResults", ns)
                if total_el is not None:
                    count = int(total_el.text or "0")
                    return VerifiedSource(verified=count > 0, sample_count=count)
            except Exception:
                pass

        return VerifiedSource(verified=False)

    async def fetch(self, source: ResolvedSource) -> list[FetchedArticle]:
        sq = source.query_json.get("search_query", "")
        max_results = source.query_json.get("max_results", "50")
        if not sq:
            return []

        client = await self._get_client()
        try:
            resp = await client.get(
                ARXIV_API_BASE,
                params={"search_query": sq, "max_results": max_results, "sortBy": "submittedDate"},
                timeout=15,
            )
        except Exception:
            return []

        if resp.status_code != 200:
            return []

        import feedparser

        feed = feedparser.parse(resp.text)
        articles: list[FetchedArticle] = []
        for entry in feed.entries:
            article_url = entry.get("link", "")
            if not article_url:
                continue
            articles.append(
                FetchedArticle(
                    external_id=entry.get("id", article_url),
                    title=entry.get("title", ""),
                    url=article_url,
                    summary=entry.get("summary", ""),
                    author=entry.get("author"),
                    published_at=entry.get("published"),
                )
            )
        return articles
