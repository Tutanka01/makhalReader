import json
import os
import re
from typing import Optional

import httpx

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
QA_MODEL = os.getenv("QA_MODEL", os.getenv("SCORER_MODEL", "google/gemini-flash-1.5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")


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


def _use_openrouter() -> bool:
    return bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"))


async def complete_json(
    messages: list[dict],
    *,
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> Optional[dict]:
    """Run one non-streaming chat completion and return the parsed JSON object, or None."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            if _use_openrouter():
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "X-Title": "MakhalReader",
                    },
                    json={
                        "model": QA_MODEL,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
                if not resp.is_success:
                    print(f"[briefing] OpenRouter error {resp.status_code}: {resp.text[:300]}")
                    return None
                content = resp.json()["choices"][0]["message"]["content"]
            else:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
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
