from __future__ import annotations

from typing import Optional

import httpx

from net_guard import SSRFBlockedError, check_url

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource


class GenericRSSProvider(SourceProvider):
    provider_id = "rss"

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=15.0)

    async def resolve(self, intent: SourceIntent) -> list[ResolvedSource]:
        url = intent.query.strip()
        if not url:
            return []
        return [
            ResolvedSource(
                name=url,
                provider="rss",
                query_json={"url": url},
                label="rss",
                provenance_url=url,
                category="rss",
            )
        ]

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        url = source.query_json.get("url", "")
        if not url:
            return VerifiedSource(verified=False, message="no URL")

        try:
            check_url(url)
        except SSRFBlockedError:
            return VerifiedSource(verified=False, message="SSRF blocked")

        client = await self._get_client()
        try:
            resp = await client.get(url, follow_redirects=True, timeout=15)
        except Exception as exc:
            return VerifiedSource(verified=False, message=str(exc))

        if resp.status_code != 200:
            return VerifiedSource(verified=False, message=f"HTTP {resp.status_code}")

        body = resp.text[:2000].lower()
        is_rss = "<rss" in body or "<feed" in body or 'xmlns="http://www.w3.org/2005/atom"' in body
        if not is_rss:
            return VerifiedSource(verified=False, message="not a feed")

        return VerifiedSource(verified=True, sample_count=1, message="feed OK")
