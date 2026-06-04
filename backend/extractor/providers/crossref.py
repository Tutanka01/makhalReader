from __future__ import annotations

from typing import Optional

import httpx

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

CROSSREF_BASE_URL = "https://api.crossref.org"
CROSSREF_USER_AGENT = "Basira/1.0 (mailto:arona.fall@alouette.ai)"
_CROSSREF_HEADERS = {"User-Agent": CROSSREF_USER_AGENT}


async def fetch_crossref_work(
    doi: str, client: httpx.AsyncClient
) -> Optional[dict]:
    """Fetch a Crossref work by DOI. Returns the message dict or None."""
    try:
        resp = await client.get(
            f"{CROSSREF_BASE_URL}/works/{doi}",
            headers=_CROSSREF_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return (resp.json().get("message") or {})
    except Exception:
        return None


class CrossrefProvider(SourceProvider):
    provider_id = "crossref"

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient()

    async def resolve(self, intent: SourceIntent) -> list[ResolvedSource]:
        query = intent.query.strip()
        if not query:
            return []

        results: list[ResolvedSource] = []
        seen_titles: set[str] = set()
        client = await self._get_client()

        resp = await client.get(
            f"{CROSSREF_BASE_URL}/works",
            params={"query": query, "rows": "10"},
            headers=_CROSSREF_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return results

        for item in (resp.json().get("message") or {}).get("items") or []:
            titles = item.get("title") or []
            title = titles[0] if titles else ""
            if not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())

            doi = (item.get("DOI") or "").strip()
            provenance = f"https://doi.org/{doi}" if doi else ""
            results.append(ResolvedSource(
                name=title,
                provider="crossref",
                query_json={"doi": doi, "query": query} if doi else {"query": query},
                label="article",
                provenance_url=provenance,
                category="work",
            ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        doi = source.query_json.get("doi", "")
        if not doi:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        msg = await fetch_crossref_work(doi, client)
        if not msg:
            return VerifiedSource(verified=False)

        titles = msg.get("title") or []
        verified = bool(titles and titles[0])
        return VerifiedSource(
            verified=verified,
            sample_count=1 if verified else 0,
            message="DOI resolved" if verified else "DOI not found",
        )
