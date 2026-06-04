from __future__ import annotations

from typing import Optional

import httpx

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

OPENREVIEW_BASE = "https://api.openreview.net"


class OpenReviewProvider(SourceProvider):
    provider_id = "openreview"

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
            f"{OPENREVIEW_BASE}/venues",
            timeout=15,
        )
        if resp.status_code != 200:
            return results

        venues = (resp.json().get("venues") or [])
        for venue in venues[:10]:
            vname = (venue.get("id") or "").lower()
            if query.lower() not in vname:
                continue
            results.append(ResolvedSource(
                name=venue.get("id", query),
                provider="openreview",
                query_json={"invitation": venue.get("id", ""), "query": query},
                label="openreview_venue",
                provenance_url=f"https://openreview.net/group?id={venue.get('id', '')}",
                category="conference",
            ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        invitation = source.query_json.get("invitation", "")
        if not invitation:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        try:
            resp = await client.get(
                f"{OPENREVIEW_BASE}/notes",
                params={"invitation": invitation, "limit": 1},
                timeout=15,
            )
        except Exception:
            return VerifiedSource(verified=False)

        if resp.status_code != 200:
            return VerifiedSource(verified=False)

        count = (resp.json().get("count") or 0)
        notes = resp.json().get("notes") or []
        return VerifiedSource(
            verified=len(notes) > 0,
            sample_count=count or len(notes),
        )
