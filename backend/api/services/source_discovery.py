"""Story 13.1—13.2 — Discovery EXPAND + RESOLVE/VERIFY/RANK pipeline.

Pure async function that takes a free-text thesis description and returns a
structured ExpandResult (field label, concepts, venue/author keywords, query
terms, language) via one LLM call. Then resolves through all configured providers,
verifies each candidate, and ranks by relevance.

Constraints:
- FR-MT-59: LLM contract forbids URLs/DOIs/IDs; Pydantic validator strips any
  that leak through.
- NFR-DA6: SHA-256 in-memory cache with 3600s TTL.
- NFR-DA9: any failure returns a degraded ExpandResult — never raises.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx
import structlog
from pydantic import BaseModel, field_validator

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXPAND_CACHE_TTL_SECONDS = 3600.0

UNI_OLLAMA_URL = os.getenv("UNI_OLLAMA_URL", "").strip().rstrip("/")
UNI_OLLAMA_MODEL = os.getenv("UNI_OLLAMA_MODEL", "").strip()
UNI_OLLAMA_API_KEY = os.getenv("UNI_OLLAMA_API_KEY", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host-gateway:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SCORER_MODEL = os.getenv("SCORER_MODEL", "google/gemini-flash-1.5")

_DOI_RE = re.compile(r"10\.\d{4,}/\S+")


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_CTRL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize(text: str) -> str:
    if not text:
        return ""
    return _CTRL_CHAR_RE.sub("", text).replace("\n", " ").replace("\r", " ").strip()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExpandResult(BaseModel):
    field_label: str = ""
    concepts: List[str] = []
    venue_keywords: List[str] = []
    author_keywords: List[str] = []
    query_terms: List[str] = []
    language: str = ""
    degraded: bool = False

    @field_validator("concepts", "venue_keywords", "author_keywords", "query_terms", mode="before")
    @classmethod
    def _strip_urls_and_dois(cls, v: object) -> object:
        if not isinstance(v, list):
            return v
        cleaned: List[str] = []
        for item in v:
            if not isinstance(item, str):
                cleaned.append(item)
                continue
            if _has_url_or_doi(item):
                continue
            cleaned.append(item)
        return cleaned


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _has_url_or_doi(value: str) -> bool:
    if _URL_RE.search(value):
        return True
    if "doi.org" in value.lower():
        return True
    if _DOI_RE.search(value):
        return True
    return False


def _degraded_result(thesis_text: str) -> ExpandResult:
    return ExpandResult(
        field_label=thesis_text[:40],
        degraded=True,
    )


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_cache: dict[str, Tuple[ExpandResult, float]] = {}


def _cache_get(key: str) -> Optional[ExpandResult]:
    entry = _cache.get(key)
    if entry is None:
        return None
    result, ts = entry
    if (time.monotonic() - ts) > EXPAND_CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return result


def _cache_put(key: str, result: ExpandResult) -> None:
    if result.degraded:
        return
    _cache[key] = (result, time.monotonic())


def cache_clear() -> None:
    _cache.clear()


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_EXPAND_SYSTEM = (
    "You are a research domain classifier. Given the thesis description below, extract:\n"
    "- field_label: a concise label for the research domain (e.g., 'Computational Linguistics')\n"
    "- concepts: key domain concepts (max 10 terms)\n"
    "- venue_keywords: journal/conference name keywords (max 10)\n"
    "- author_keywords: researcher name fragments to search (max 5)\n"
    "- query_terms: Boolean search query terms (max 10)\n"
    "- language: primary language of the field (e.g., 'en')\n\n"
    "IMPORTANT: Do NOT include any URLs, DOIs, arXiv IDs, PubMed IDs, web addresses, "
    "or any identifiers in your response. Only plain text labels and keywords.\n\n"
    "Respond only with valid JSON matching the schema above.\n\n"
    "Thesis: {thesis_text}"
)


# ---------------------------------------------------------------------------
# LLM routing — 3-tier (uni → local Ollama → OpenRouter)
# ---------------------------------------------------------------------------


async def _chat_uni(client: httpx.AsyncClient, user: str) -> Optional[str]:
    if not UNI_OLLAMA_URL or not UNI_OLLAMA_MODEL:
        return None
    headers = {"Content-Type": "application/json"}
    if UNI_OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {UNI_OLLAMA_API_KEY}"
    try:
        r = await client.post(
            f"{UNI_OLLAMA_URL}/chat/completions",
            headers=headers,
            json={
                "model": UNI_OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _EXPAND_SYSTEM},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=30.0,
        )
        if r.is_success:
            return r.json()["choices"][0]["message"]["content"]
        logger.warning("expand_uni_http", status=r.status_code)
    except Exception as e:
        logger.warning("expand_uni_failed", error=str(e))
    return None


async def _chat_ollama(client: httpx.AsyncClient, user: str) -> Optional[str]:
    try:
        r = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _EXPAND_SYSTEM},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 2048},
            },
            timeout=30.0,
        )
        if r.is_success:
            return r.json().get("message", {}).get("content")
        logger.warning("expand_ollama_http", status=r.status_code)
    except Exception as e:
        logger.warning("expand_ollama_failed", error=str(e))
    return None


async def _chat_openrouter(client: httpx.AsyncClient, user: str) -> Optional[str]:
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-"):
        return None
    try:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/basira",
                "X-Title": "Basira",
            },
            json={
                "model": SCORER_MODEL,
                "messages": [
                    {"role": "system", "content": _EXPAND_SYSTEM},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=30.0,
        )
        if r.is_success:
            return r.json()["choices"][0]["message"]["content"]
        logger.warning("expand_openrouter_http", status=r.status_code)
    except Exception as e:
        logger.warning("expand_openrouter_failed", error=str(e))
    return None


async def _call_llm(user_message: str) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        content = await _chat_uni(client, user_message)
        if content:
            return content
        content = await _chat_ollama(client, user_message)
        if content:
            return content
        content = await _chat_openrouter(client, user_message)
        if content:
            return content
    return None


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _extract_json_object(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None
    fence = _FENCE_RE.search(text)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    depth = 0
    start = None
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    parsed = json.loads(text[start : i + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    start = None
                    continue
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def expand(thesis_text: str) -> ExpandResult:
    sanitized = sanitize(thesis_text)
    if not sanitized:
        return _degraded_result(thesis_text)

    cache_key = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("expand_cache_hit", key_prefix=cache_key[:8])
        return cached

    t0 = time.perf_counter()
    try:
        content = await _call_llm(sanitized)
    except Exception as e:
        logger.warning("expand_llm_exception", error=str(e), latency_ms=int((time.perf_counter() - t0) * 1000))
        return _degraded_result(thesis_text)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if not content:
        logger.warning("expand_llm_unavailable", latency_ms=elapsed_ms)
        return _degraded_result(thesis_text)

    parsed = _extract_json_object(content)
    if parsed is None:
        logger.warning("expand_bad_json", latency_ms=elapsed_ms)
        return _degraded_result(thesis_text)

    try:
        result = ExpandResult.model_validate(parsed)
    except Exception as e:
        logger.warning("expand_validation_failed", error=str(e), latency_ms=elapsed_ms)
        return _degraded_result(thesis_text)

    logger.info("expand_ok", latency_ms=elapsed_ms, concepts=len(result.concepts))
    _cache_put(cache_key, result)
    return result


# ===========================================================================
# Story 13.2 — RESOLVE / VERIFY / RANK pipeline
# ===========================================================================

# ---------------------------------------------------------------------------
# Pipeline models
# ---------------------------------------------------------------------------


class DiscoveryCandidate(BaseModel):
    """A single resolved source before verification."""
    name: str
    provider: str
    query_json: dict = {}
    provenance_url: str = ""
    relevance_score: float = 0.0
    verified: bool = False
    unverifiable: bool = False
    label: str = ""


class DiscoveredItem(BaseModel):
    """A fully verified-and-ranked item in the final pack."""
    name: str
    provider: str
    query_json: dict = {}
    provenance_url: str = ""
    verified: bool = False
    label: str = ""
    unverifiable: bool = False


class DiscoveryPack(BaseModel):
    """The final output of the discovery pipeline."""
    sources: List[DiscoveredItem] = []
    venues: List[DiscoveredItem] = []
    authors: List[DiscoveredItem] = []


# ---------------------------------------------------------------------------
# RESOLVE — query all registered providers with EXPAND keywords
# ---------------------------------------------------------------------------

MAX_CANDIDATES = 60
_VERIFY_TIMEOUT = 10.0

_RESOLVE_QUERY_KEYS: Dict[str, str] = {
    "openalex": "concepts",
    "crossref": "query_terms",
    "arxiv": "concepts",
    "doaj": "venue_keywords",
    "hal": "venue_keywords",
    "dblp": "venue_keywords",
    "openreview": "venue_keywords",
}


async def _resolve_one(
    provider_id: str,
    provider_cls: type,
    keyword: str,
    client: httpx.AsyncClient,
) -> List[DiscoveryCandidate]:
    """Call a single provider with a single keyword and map results."""
    try:
        from providers.base import SourceIntent
        provider = provider_cls()
        intent = SourceIntent(query=keyword)
        results = await provider.resolve(intent)
        return [
            DiscoveryCandidate(
                name=r.name,
                provider=r.provider,
                query_json=r.query_json or {},
                provenance_url=r.provenance_url or "",
                relevance_score=1.0,
                label=r.label or "",
            )
            for r in results
        ]
    except Exception as e:
        logger.warning("resolve_one_failed", provider=provider_id, keyword=keyword[:30], error=str(e))
        return []


async def _resolve_all(expand_result: ExpandResult) -> List[DiscoveryCandidate]:
    """Query all registered providers with keywords from ExpandResult.

    Pairs providers with their strongest keyword category from the expand
    output, then calls resolve concurrently. Deduplicates by (name, provider)
    and accumulates relevance score per duplicate.
    """
    from providers import PROVIDER_REGISTRY

    keyword_buckets: Dict[str, List[str]] = {}
    for pid, key_attr in _RESOLVE_QUERY_KEYS.items():
        keywords = getattr(expand_result, key_attr, [])
        if keywords:
            keyword_buckets[pid] = keywords
        elif pid in PROVIDER_REGISTRY:
            keyword_buckets[pid] = expand_result.concepts or [expand_result.field_label]

    tasks = []
    async with httpx.AsyncClient() as client:
        for pid, keywords in keyword_buckets.items():
            if pid not in PROVIDER_REGISTRY:
                continue
            p_cls = PROVIDER_REGISTRY[pid]
            for kw in keywords:
                tasks.append(_resolve_one(pid, p_cls, kw, client))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten, filter exceptions, dedup + aggregate score
    seen: Dict[Tuple[str, str], DiscoveryCandidate] = {}
    for batch in all_results:
        if not isinstance(batch, list):
            continue
        for c in batch:
            key = (c.name, c.provider)
            if key in seen:
                seen[key].relevance_score += c.relevance_score
            else:
                seen[key] = c

    candidates = sorted(seen.values(), key=lambda c: c.relevance_score, reverse=True)
    logger.info("resolve_all_done", total_raw=sum(len(b) if isinstance(b, list) else 0 for b in all_results), deduped=len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Cap — keep top N by relevance score (NFR-DA6)
# ---------------------------------------------------------------------------


def _cap_candidates(candidates: List[DiscoveryCandidate]) -> List[DiscoveryCandidate]:
    if len(candidates) <= MAX_CANDIDATES:
        logger.info("cap_no_op", count=len(candidates))
        return candidates
    kept = candidates[:MAX_CANDIDATES]
    logger.info("cap_applied", before=len(candidates), after=MAX_CANDIDATES)
    return kept


# ---------------------------------------------------------------------------
# VERIFY — concurrent HTTP check of each candidate's provenance URL
# ---------------------------------------------------------------------------


async def _verify_one(candidate: DiscoveryCandidate) -> DiscoveryCandidate:
    if not candidate.provenance_url:
        candidate.unverifiable = True
        return candidate

    try:
        from net_guard import check_url
        check_url(candidate.provenance_url)
    except Exception:
        candidate.unverifiable = True
        return candidate

    try:
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT) as c:
            r = await c.head(candidate.provenance_url, follow_redirects=True)
            candidate.verified = r.is_success
    except httpx.TimeoutException:
        candidate.unverifiable = True
    except httpx.ConnectError:
        candidate.verified = False
    except Exception:
        candidate.verified = False
    return candidate


async def _verify_all(candidates: List[DiscoveryCandidate]) -> List[DiscoveryCandidate]:
    tasks = [_verify_one(c) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final = []
    for r in results:
        if isinstance(r, DiscoveryCandidate):
            final.append(r)
    verified_count = sum(1 for c in final if c.verified)
    unverifiable_count = sum(1 for c in final if c.unverifiable)
    logger.info("verify_done", total=len(final), verified=verified_count, unverifiable=unverifiable_count)
    return final


# ---------------------------------------------------------------------------
# RANK — sort verified items and group into DiscoveryPack
# ---------------------------------------------------------------------------


def _rank_and_group(candidates: List[DiscoveryCandidate]) -> DiscoveryPack:
    sorted_c = sorted(candidates, key=lambda c: c.relevance_score, reverse=True)
    pack = DiscoveryPack()
    for c in sorted_c:
        item = DiscoveredItem(
            name=c.name,
            provider=c.provider,
            query_json=c.query_json,
            provenance_url=c.provenance_url,
            verified=c.verified,
            label=c.label,
            unverifiable=c.unverifiable,
        )
        if c.label in ("journal", "conference", "venue"):
            pack.venues.append(item)
        elif c.label == "author":
            pack.authors.append(item)
        else:
            pack.sources.append(item)
    logger.info("rank_done", sources=len(pack.sources), venues=len(pack.venues), authors=len(pack.authors))
    return pack


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


async def resolve_verify_rank(expand_result: ExpandResult) -> DiscoveryPack:
    """Run the full discovery pipeline on an ExpandResult.

    Steps: resolve → cap → verify → rank. Never raises; on total failure
    returns an empty DiscoveryPack.
    """
    try:
        candidates = await _resolve_all(expand_result)
        capped = _cap_candidates(candidates)
        verified = await _verify_all(capped)
        return _rank_and_group(verified)
    except Exception as e:
        logger.error("pipeline_failed", error=str(e))
        return DiscoveryPack()
