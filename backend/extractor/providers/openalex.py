from __future__ import annotations

import asyncio
import time
from typing import Optional

import httpx

from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_USER_AGENT = "Basira/1.0 (mailto:arona.fall@alouette.ai)"
OPENALEX_RATE_LIMIT_SECONDS = 0.1

_OPENALEX_HEADERS = {"User-Agent": OPENALEX_USER_AGENT}
_OPENALEX_LOCK = asyncio.Lock()
_openalex_last_call: float = 0.0


async def _openalex_rate_limited_get(
    client: httpx.AsyncClient, url: str, params: Optional[dict] = None
) -> Optional[httpx.Response]:
    global _openalex_last_call
    async with _OPENALEX_LOCK:
        elapsed = time.monotonic() - _openalex_last_call
        if elapsed < OPENALEX_RATE_LIMIT_SECONDS:
            await asyncio.sleep(OPENALEX_RATE_LIMIT_SECONDS - elapsed)
        try:
            resp = await client.get(url, params=params, headers=_OPENALEX_HEADERS, timeout=10)
            return resp
        except Exception:
            return None
        finally:
            _openalex_last_call = time.monotonic()


class OpenAlexProvider(SourceProvider):
    provider_id = "openalex"

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
        seen: set[str] = set()
        client = await self._get_client()

        resp = await _openalex_rate_limited_get(
            client, f"{OPENALEX_BASE_URL}/sources", params={"search": query, "per_page": "10"}
        )
        if resp and resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                sid = item.get("id", "")
                if sid in seen:
                    continue
                seen.add(sid)
                results.append(ResolvedSource(
                    name=item.get("display_name", query),
                    provider="openalex",
                    query_json={"source_id": sid, "search": query},
                    label=item.get("type") or "journal",
                    provenance_url=sid,
                    category="journal",
                ))

        resp = await _openalex_rate_limited_get(
            client, f"{OPENALEX_BASE_URL}/concepts", params={"search": query, "per_page": "5"}
        )
        if resp and resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                cid = item.get("id", "")
                if cid in seen:
                    continue
                seen.add(cid)
                results.append(ResolvedSource(
                    name=item.get("display_name", query),
                    provider="openalex",
                    query_json={"concept_id": cid, "search": query},
                    label="concept",
                    provenance_url=cid,
                    category="concept",
                ))

        return results

    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        filters = []
        if "concept_id" in source.query_json:
            filters.append(f"concepts.id:{source.query_json['concept_id']}")
        elif "source_id" in source.query_json:
            filters.append(f"primary_location.source.id:{source.query_json['source_id']}")
        else:
            return VerifiedSource(verified=False)

        client = await self._get_client()
        resp = await _openalex_rate_limited_get(
            client,
            f"{OPENALEX_BASE_URL}/works",
            params={"filter": ",".join(filters), "sort": "publication_date:desc", "per_page": "1"},
        )
        if not resp or resp.status_code != 200:
            return VerifiedSource(verified=False)

        count = (resp.json().get("meta") or {}).get("count", 0) or 0
        return VerifiedSource(
            verified=count > 0,
            sample_count=count,
        )
