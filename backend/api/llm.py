import json
import os
import re
from typing import Optional

import httpx

# Generic OpenAI-compatible endpoint (highest priority when set): point it at any
# OpenAI-compatible server (vLLM, llama.cpp, LM Studio, Groq, Together, OpenAI…).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
QA_MODEL = os.getenv("QA_MODEL", os.getenv("SCORER_MODEL", "google/gemini-flash-1.5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")


def _chat_completions_url(base: str) -> str:
    """Build the chat-completions URL from a base, forgiving about how it's written."""
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def resolve_provider() -> tuple[str, str, str, str]:
    """Pick the LLM provider. Returns (kind, url, api_key, model).

    kind is 'openai' (OpenAI-compatible chat-completions) or 'ollama'.
    Priority — an explicit OpenAI-compatible endpoint wins exclusively; otherwise
    the default is OpenRouter (if its key starts with sk-), then Ollama.
    """
    if LLM_BASE_URL:
        return ("openai", _chat_completions_url(LLM_BASE_URL), LLM_API_KEY, LLM_MODEL)
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"):
        return ("openai", "https://openrouter.ai/api/v1/chat/completions", OPENROUTER_API_KEY, QA_MODEL)
    return ("ollama", OLLAMA_URL, "", OLLAMA_MODEL)


def _repair(text: str) -> str:
    # Drop trailing commas before } or ]
    return re.sub(r",\s*([}\]])", r"\1", text.strip())


def extract_json(text: str) -> Optional[dict]:
    """Extract a JSON object from raw LLM text (handles ``` fences and trailing commas)."""
    candidates = [text.strip()]
    for pattern in (r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"):
        candidates += [m.strip() for m in re.findall(pattern, text)]
    first, last = text.find("{"), text.rfind("}")
    if 0 <= first < last:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        for maybe in (candidate, _repair(candidate)):
            try:
                parsed = json.loads(maybe)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


async def complete_json(
    messages: list[dict],
    *,
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> Optional[dict]:
    """Run one non-streaming chat completion and return the parsed JSON object, or None."""
    kind, url, api_key, model = resolve_provider()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            if kind == "openai":
                headers = {"Content-Type": "application/json", "X-Title": "MakhalReader"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
                if not resp.is_success:
                    print(f"[briefing] LLM endpoint error {resp.status_code}: {resp.text[:300]}")
                    return None
                content = resp.json()["choices"][0]["message"]["content"]
            else:
                resp = await client.post(
                    f"{url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": temperature, "num_predict": max_tokens},
                    },
                )
                if not resp.is_success:
                    print(f"[briefing] Ollama error {resp.status_code}: {resp.text[:300]}")
                    return None
                content = resp.json()["message"]["content"]
        return extract_json(content)
    except Exception as e:  # noqa: BLE001
        print(f"[briefing] LLM call failed: {e}")
        return None
