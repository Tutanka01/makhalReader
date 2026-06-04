from __future__ import annotations

from typing import Optional

import httpx

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

DOAJ_BASE = "https://doaj.org/api/v2"


class DoajProvider(SourceProvider):
    provider_id = "doaj"

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
            f"{DOAJ_BASE}/search/journals/{query}",
            params={"pageSize": 10, "page": 1},
            timeout=15,
        )
        if resp.status_code != 200:
            return results

        for item in (resp.json().get("results") or []):
            bj = item.get("bibjson") or {}
            issn_list = []
            for k in ("pissn", "eissn"):
                v = bj.get(k)
                if v:
                    issn_list.append(v)
            issn = issn_list[0] if issn_list else ""
            results.append(ResolvedSource(
                name=bj.get("title", query),
                provider="doaj",
                query_json={"issn": issn, "query": query, "journal_id": item.get("id", "")},
                label="journal",
                provenance_url=f"https://doaj.org/toc/{issn}" if issn else "",
                category="journal",
            ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        jid = source.query_json.get("journal_id", "")
        if not jid:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        try:
            resp = await client.get(f"{DOAJ_BASE}/journals/{jid}", timeout=15)
        except Exception:
            return VerifiedSource(verified=False)

        if resp.status_code != 200:
            return VerifiedSource(verified=False)

        data = resp.json()
        last_updated = (data.get("last_updated_timestamp") or 0) / 1000
        import time
        is_active = data.get("bibjson", {}).get("active", False)
        return VerifiedSource(
            verified=bool(is_active),
            sample_count=1,
            message="active" if is_active else "inactive",
        )
