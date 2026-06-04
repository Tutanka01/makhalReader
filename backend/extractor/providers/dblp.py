from __future__ import annotations

from typing import Optional

import httpx

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

DBLP_BASE = "https://dblp.org"


class DblpProvider(SourceProvider):
    provider_id = "dblp"

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

        client = await self._get_client()
        results: list[ResolvedSource] = []

        resp = await client.get(
            f"{DBLP_BASE}/search/publ/api",
            params={"q": query, "format": "json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return results

        data = resp.json()
        hits = ((data.get("result") or {}).get("hits") or {}).get("hit") or []
        for hit in hits[:10]:
            info = hit.get("info") or {}
            venue = info.get("venue", "") or ""
            url = info.get("url", "") or ""
            year = info.get("year", "")
            results.append(ResolvedSource(
                name=info.get("title", query),
                provider="dblp",
                query_json={"url": url, "venue": venue, "year": year, "query": query},
                label="dblp_publication",
                provenance_url=url,
                category="publication",
            ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        url = source.query_json.get("url", "")
        if not url:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        try:
            resp = await client.get(url, timeout=15)
        except Exception:
            return VerifiedSource(verified=False)

        return VerifiedSource(
            verified=resp.status_code == 200,
            sample_count=1 if resp.status_code == 200 else 0,
        )
