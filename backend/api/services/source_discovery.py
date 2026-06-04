"""Story 13.1 — Discovery EXPAND stage.

Pure async function that takes a free-text thesis description and returns a
structured ExpandResult (field label, concepts, venue/author keywords, query
terms, language) via one LLM call.

Constraints:
- FR-MT-59: LLM contract forbids URLs/DOIs/IDs; Pydantic validator strips any
  that leak through.
- NFR-DA6: SHA-256 in-memory cache with 3600s TTL.
- NFR-DA9: any failure returns a degraded ExpandResult — never raises.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import List, Optional, Tuple

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
