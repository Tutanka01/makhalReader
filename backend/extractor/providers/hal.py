from __future__ import annotations

from typing import Optional

import httpx

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

HAL_BASE = "https://api.archives-ouvertes.fr"


class HalProvider(SourceProvider):
    provider_id = "hal"

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
            f"{HAL_BASE}/search/",
            params={"q": query, "rows": 5, "wt": "json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return results

        data = resp.json()
        for doc in (data.get("response") or {}).get("docs") or []:
            doc_id = doc.get("docid") or doc.get("halId", "")
            struct = doc.get("struct", "")
            label = doc.get("label_s", "") or doc.get("journalTitle_s", "") or struct
            results.append(ResolvedSource(
                name=label or doc.get("title_s", [query])[0] if isinstance(doc.get("title_s"), list) else query,
                provider="hal",
                query_json={"docid": doc_id, "query": query},
                label="hal_publication",
                provenance_url=f"https://hal.science/{doc_id}" if doc_id else "",
                category="open_access",
            ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        docid = source.query_json.get("docid", "")
        if not docid:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        try:
            resp = await client.get(
                f"{HAL_BASE}/search/",
                params={"q": f"docid:{docid}", "rows": 1, "wt": "json"},
                timeout=15,
            )
        except Exception:
            return VerifiedSource(verified=False)

        if resp.status_code != 200:
            return VerifiedSource(verified=False)

        count = (resp.json().get("response") or {}).get("numFound", 0) or 0
        return VerifiedSource(
            verified=count > 0,
            sample_count=count,
        )
