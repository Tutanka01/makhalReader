"""Tiered LLM calls for literature-review cluster synthesis (Story 3.4).

chromadb is never imported here. Tier order: university OpenAI-compatible →
local Ollama → OpenRouter (per epics).
"""
import json
import os
import re
import time
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger().bind(service="lit_review_llm")

UNI_OLLAMA_URL = os.getenv("UNI_OLLAMA_URL", "").strip().rstrip("/")
UNI_OLLAMA_MODEL = os.getenv("UNI_OLLAMA_MODEL", "").strip()
UNI_OLLAMA_API_KEY = os.getenv("UNI_OLLAMA_API_KEY", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SCORER_MODEL = os.getenv("SCORER_MODEL", "google/gemini-flash-1.5")

_UNI_HEALTH_OK_UNTIL = 0.0  # time.monotonic()


def _extract_balanced_json(text: str, start: int) -> Optional[str]:
    depth = 0
    in_string = False
    escape = False
    for i, c in enumerate(text[start:]):
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : start + i + 1]
    return None


def extract_json_from_text(text: str) -> Optional[dict]:
    """Extract JSON object from model output.

    Handles markdown code blocks, thinking preambles, and token-limit truncation
    by scanning backward from the last '{' to find the last complete JSON object.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
        for m in re.findall(pattern, text, re.DOTALL):
            try:
                result = json.loads(m)
                if isinstance(result, dict) and result:
                    return result
            except json.JSONDecodeError:
                pass
    brace_positions = [i for i, c in enumerate(text) if c == "{"]
    for start in reversed(brace_positions):
        candidate = _extract_balanced_json(text, start)
        if candidate:
            try:
                result = json.loads(candidate)
                if isinstance(result, dict) and result:
                    return result
            except json.JSONDecodeError:
                continue
    return None


async def _uni_server_healthy(client: httpx.AsyncClient) -> bool:
    """Cached 5-minute positive health for university tier."""
    global _UNI_HEALTH_OK_UNTIL
    now = time.monotonic()
    if now < _UNI_HEALTH_OK_UNTIL:
        return True
    if not UNI_OLLAMA_URL or not UNI_OLLAMA_MODEL:
        return False
    try:
        models_url = f"{UNI_OLLAMA_URL}/v1/models"
        headers = {}
        if UNI_OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {UNI_OLLAMA_API_KEY}"
        r = await client.get(models_url, headers=headers, timeout=5.0)
        if r.is_success:
            _UNI_HEALTH_OK_UNTIL = now + 300.0
            return True
    except Exception as e:
        logger.warning("uni_health_check_failed", error=str(e))
    return False


async def _chat_uni(client: httpx.AsyncClient, system: str, user: str) -> Optional[str]:
    if not await _uni_server_healthy(client):
        return None
    url = f"{UNI_OLLAMA_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if UNI_OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {UNI_OLLAMA_API_KEY}"
    try:
        r = await client.post(
            url,
            headers=headers,
            json={
                "model": UNI_OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.25,
                "max_tokens": 4096,
            },
            timeout=120.0,
        )
        if not r.is_success:
            logger.warning("uni_chat_http", status=r.status_code, body=r.text[:200])
            return None
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("uni_chat_failed", error=str(e))
        return None


async def _chat_ollama(client: httpx.AsyncClient, system: str, user: str) -> Optional[str]:
    try:
        r = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.25, "num_predict": 4096},
            },
            timeout=120.0,
        )
        if not r.is_success:
            logger.warning("ollama_chat_http", status=r.status_code, body=r.text[:200])
            return None
        return r.json().get("message", {}).get("content")
    except Exception as e:
        logger.warning("ollama_chat_failed", error=str(e))
        return None


async def _chat_openrouter(client: httpx.AsyncClient, system: str, user: str) -> Optional[str]:
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
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.25,
                "max_tokens": 4096,
            },
            timeout=120.0,
        )
        if not r.is_success:
            logger.warning("openrouter_chat_http", status=r.status_code, body=r.text[:200])
            return None
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("openrouter_chat_failed", error=str(e))
        return None


SYSTEM_JSON = """You are an expert research assistant. Output a single JSON object ONLY, no markdown, with this exact shape:
{
  "synthesis": "<one paragraph comparing the works below>",
  "comparison_table": [{"work":"","method":"","dataset":"","key_result":""}],
  "gaps": ["<gap1>","<gap2>"],
  "top_cite": "<one paper title or citation to read first>"
}
Rules: comparison_table has one row per supplied article when possible; use empty strings if unknown. gaps: at most 3 strings. Be concise."""


async def synthesize_cluster_json(
    cluster_label: str,
    user_block: str,
) -> Dict[str, Any]:
    """Run uni → ollama → openrouter; return parsed dict (may be partial on parse failure)."""
    t0 = time.perf_counter()
    tier_used = "none"
    content: Optional[str] = None
    async with httpx.AsyncClient() as client:
        content = await _chat_uni(client, SYSTEM_JSON, user_block)
        if content:
            tier_used = "uni"
        if not content:
            content = await _chat_ollama(client, SYSTEM_JSON, user_block)
            if content:
                tier_used = "local"
        if not content:
            content = await _chat_openrouter(client, SYSTEM_JSON, user_block)
            if content:
                tier_used = "openrouter"

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if not content:
        logger.info(
            "lit_review_llm_failed",
            cluster_label=cluster_label,
            lit_review_llm_tier="none",
            latency_ms=elapsed_ms,
            error="all_tiers_failed",
        )
        raise RuntimeError("all LLM tiers failed")

    parsed = extract_json_from_text(content)
    if not isinstance(parsed, dict):
        logger.warning(
            "lit_review_llm_bad_json",
            cluster_label=cluster_label,
            lit_review_llm_tier=tier_used,
            latency_ms=elapsed_ms,
        )
        raise ValueError("model did not return a JSON object")

    logger.info(
        "lit_review_llm_ok",
        cluster_label=cluster_label,
        lit_review_llm_tier=tier_used,
        latency_ms=elapsed_ms,
    )
    return parsed
