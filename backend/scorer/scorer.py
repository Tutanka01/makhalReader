import json
import os
import re
from typing import List, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from prompt import SYSTEM_PROMPT

app = FastAPI(title="MakhalReader Scorer")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SCORER_MODEL = os.getenv("SCORER_MODEL", "google/gemini-flash-1.5")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host-gateway:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
API_BASE = "http://api:8000"
API_SECRET = os.getenv("API_SECRET", "changeme")

INTERNAL_HEADERS = {"X-Internal-Secret": API_SECRET, "Content-Type": "application/json"}


class ScoreRequest(BaseModel):
    article_id: int
    title: str
    content_text: str
    rss_summary: str = ""


class ScoreResult(BaseModel):
    score: float
    tags: List[str] = []
    summary_bullets: List[str] = []
    reason: str = ""


def extract_json_from_text(text: str) -> Optional[dict]:
    """Extract JSON from text, handling markdown code blocks."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code blocks
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\{[\s\S]*\}",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match if pattern == r"\{[\s\S]*\}" else match)
            except json.JSONDecodeError:
                # Try finding JSON object inside the match
                obj_match = re.search(r"\{[\s\S]*\}", match)
                if obj_match:
                    try:
                        return json.loads(obj_match.group())
                    except json.JSONDecodeError:
                        continue

    return None


def validate_score_result(data: dict) -> ScoreResult:
    score = data.get("score", 5)
    try:
        score = float(score)
        score = max(0.0, min(10.0, score))
    except (TypeError, ValueError):
        score = 5.0

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags[:5]]

    summary_bullets = data.get("summary_bullets", [])
    if not isinstance(summary_bullets, list):
        summary_bullets = []
    summary_bullets = [str(b) for b in summary_bullets[:4]]

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    return ScoreResult(score=score, tags=tags, summary_bullets=summary_bullets, reason=reason)


async def score_with_openrouter(client: httpx.AsyncClient, user_message: str) -> Optional[ScoreResult]:
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-"):
        return None

    try:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/makhalreader",
                "X-Title": "MakhalReader",
            },
            json={
                "model": SCORER_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens": 512,
            },
            timeout=60,
        )
        if not resp.is_success:
            # Log full body so the user can see the actual OpenRouter error
            print(f"OpenRouter error {resp.status_code}: {resp.text[:500]}")
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = extract_json_from_text(content)
        if parsed:
            return validate_score_result(parsed)
        print(f"OpenRouter: could not parse JSON from response: {content[:200]}")
    except Exception as e:
        print(f"OpenRouter scoring failed: {e}")

    return None


async def score_with_ollama(client: httpx.AsyncClient, user_message: str) -> Optional[ScoreResult]:
    if not OLLAMA_URL:
        return None

    try:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 512,
                },
            },
            timeout=120,
        )
        if not resp.is_success:
            print(f"Ollama error {resp.status_code}: {resp.text[:300]}")
            return None
        data = resp.json()
        content = data["message"]["content"]
        parsed = extract_json_from_text(content)
        if parsed:
            return validate_score_result(parsed)
        print(f"Ollama: could not parse JSON from response: {content[:200]}")
    except Exception as e:
        print(f"Ollama scoring failed: {e}")

    return None


@app.post("/score")
async def score_article(req: ScoreRequest):
    # Build user message
    content_preview = (req.content_text or req.rss_summary or "")[:3000]
    user_message = f"Titre: {req.title}\n\nContenu:\n{content_preview}"

    result: Optional[ScoreResult] = None

    async with httpx.AsyncClient() as client:
        # Try OpenRouter first
        if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"):
            result = await score_with_openrouter(client, user_message)

        # Fallback to Ollama
        if result is None:
            result = await score_with_ollama(client, user_message)

        # Default fallback
        if result is None:
            result = ScoreResult(
                score=5.0,
                tags=[],
                summary_bullets=[],
                reason="Scoring failed: unable to reach any LLM service.",
            )

        # Post result back to API
        try:
            resp = await client.post(
                f"{API_BASE}/api/internal/articles/{req.article_id}/score",
                json={
                    "score": result.score,
                    "tags": result.tags,
                    "summary_bullets": result.summary_bullets,
                    "reason": result.reason,
                },
                headers=INTERNAL_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"Failed to post score to API: {e}")
            raise

    return {"status": "ok", "score": result.score}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
