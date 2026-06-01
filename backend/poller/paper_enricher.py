"""
Paper metadata enricher for Baṣīra poller.

Runs AFTER the extractor (HTML-based extraction + structured API calls) and
BEFORE create_article. Makes a single cheap Ollama chat call to classify the
abstract into contribution_type and re_document_type.

Contract:
- is_paper_url(url) → True if URL matches any known paper source pattern (no I/O, < 1ms)
- enrich_paper_meta(url, extraction_result, client) → dict or {}
  - Returns {} for non-paper URLs in < 50ms (no external API calls)
  - Returns paper_meta dict on success (merged from extractor data + Ollama classification)
  - Returns {"is_paper": true, "source": "fallback"} if Ollama fails but paper is detected
  - Never raises — all exceptions are caught
"""
import json
import os

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

_PAPER_PATTERNS = [
    "arxiv.org/abs/",
    "semanticscholar.org/paper/",
    "openreview.net/forum",
    "aclanthology.org/",
    "doi.org/",
    "sci-hub.",
]

_CLASSIFICATION_PROMPT = (
    "Given this research paper abstract, return a JSON object with ONLY these three fields:\n"
    '- "contribution_type": one of '
    '"method", "benchmark", "survey", "empirical", '
    '"theory", "position", "tool", "other"\n'
    '- "re_document_type": one of '
    '"elicitation", "extraction", "method", "none" '
    "(is this paper about Requirements Engineering?)\n"
    '- "confidence": float 0.0 to 1.0\n\n'
    "Abstract:\n{abstract}\n\n"
    "Reply with valid JSON only. No markdown, no code block, no extra text."
)


def is_paper_url(url: str) -> bool:
    """Return True if URL matches any known paper source pattern.

    Fast path: no I/O, must complete in < 1ms.
    """
    lower = url.lower()
    return any(p in lower for p in _PAPER_PATTERNS)


async def _classify_with_ollama(
    abstract: str, client: httpx.AsyncClient
) -> dict:
    """Make a single cheap Ollama chat call to classify the abstract.

    Returns a dict with contribution_type, re_document_type, confidence.
    Raises on network/parse error — caller is responsible for catching.
    """
    prompt = _CLASSIFICATION_PROMPT.format(abstract=abstract[:2000])
    resp = await client.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"].strip()
    # Strip markdown code fence if Ollama wraps the JSON
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def enrich_paper_meta(
    url: str,
    extraction_result: dict,
    client: httpx.AsyncClient,
) -> dict:
    """
    Enrich paper metadata with Ollama classification.

    - Non-paper URLs: returns {} in < 50ms (no API calls).
    - Paper URLs with paper_meta from extractor: calls Ollama to classify.
    - On any failure: returns minimal fallback dict so the article is not lost.
    """
    if not is_paper_url(url):
        return {}

    paper_meta: dict = dict(extraction_result.get("paper_meta") or {})

    if not paper_meta.get("is_paper"):
        # Extractor didn't detect it as a paper (handler failed/no paper_meta)
        return {"is_paper": True, "source": "fallback"}

    abstract: str = paper_meta.get("abstract") or extraction_result.get("content_text") or ""
    if not abstract:
        return {
            "is_paper": True,
            "source": paper_meta.get("source", "fallback"),
            "paper_id": paper_meta.get("paper_id"),
        }

    try:
        classification = await _classify_with_ollama(abstract, client)
        for key in ("contribution_type", "re_document_type", "confidence"):
            if key in classification and classification[key] is not None:
                paper_meta[key] = classification[key]
    except Exception:
        # Graceful degradation — paper_meta still contains structural data
        # from the extractor; the scorer will attempt its own classification.
        pass

    return paper_meta
