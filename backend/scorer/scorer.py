import json
import os
import re
from typing import List, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from prompt import SYSTEM_PROMPT
from scorer_logic import (
    _VALID_CONTRIBUTION_TYPES,
    _VALID_RE_DOC_TYPES,
    clamp_float as _clamp_float,
    compute_content_cap,
)

app = FastAPI(title="Baṣīra Scorer")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SCORER_MODEL = os.getenv("SCORER_MODEL", "google/gemini-flash-1.5")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host-gateway:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
UNI_OLLAMA_URL = os.getenv("UNI_OLLAMA_URL", "")
UNI_OLLAMA_MODEL = os.getenv("UNI_OLLAMA_MODEL", "")
UNI_OLLAMA_API_KEY = os.getenv("UNI_OLLAMA_API_KEY", "")
SCORER_MAX_CHARS = int(os.getenv("SCORER_MAX_CHARS", "6000"))
API_BASE = "http://api:8000"
API_SECRET = os.getenv("API_SECRET", "changeme")

INTERNAL_HEADERS = {"X-Internal-Secret": API_SECRET, "Content-Type": "application/json"}


class ScoreRequest(BaseModel):
    article_id: int
    title: str
    content_text: str
    rss_summary: str = ""
    paper_meta_json: Optional[str] = None
    user_id: int  # Story 2.7, FR-MT-9 — mandatory


class ScoreResult(BaseModel):
    score: float
    tags: List[str] = []
    summary_bullets: List[str] = []
    reason: str = ""
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    novelty: Optional[float] = None
    rigor: Optional[float] = None
    relevance_to_topics: Optional[float] = None


def _extract_balanced_json(text: str, start: int) -> Optional[str]:
    """Return the substring of `text` that forms a balanced JSON object starting at `start`."""
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
    """Extract a JSON object from model output.

    Handles: plain JSON, markdown code blocks, preamble/thinking text,
    and responses truncated mid-string at a token limit (scans backward
    from the last '{' so a complete outer object is preferred over a
    fragment inside a truncated response).
    """
    text = text.strip()

    # 1. Direct parse — fastest path for well-behaved models
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from markdown code blocks
    for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
        for m in re.findall(pattern, text, re.DOTALL):
            try:
                result = json.loads(m)
                if isinstance(result, dict) and result:
                    return result
            except json.JSONDecodeError:
                pass

    # 3. Balanced-brace scan — scans BACKWARD so the last complete JSON object
    #    wins.  This handles models that emit <thinking>...</thinking> preamble
    #    (which may contain '{...}' fragments) before the actual JSON response,
    #    and also handles token-limit truncation where earlier inner objects may
    #    be complete while the outer object is not.
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

    contribution_type = data.get("contribution_type")
    if contribution_type not in _VALID_CONTRIBUTION_TYPES:
        contribution_type = None

    re_document_type = data.get("re_document_type")
    if re_document_type not in _VALID_RE_DOC_TYPES:
        re_document_type = None

    return ScoreResult(
        score=score,
        tags=tags,
        summary_bullets=summary_bullets,
        reason=reason,
        contribution_type=contribution_type,
        re_document_type=re_document_type,
        novelty=_clamp_float(data.get("novelty")),
        rigor=_clamp_float(data.get("rigor")),
        relevance_to_topics=_clamp_float(data.get("relevance_to_topics")),
    )


async def score_with_uni_server(client: httpx.AsyncClient, user_message: str) -> Optional[ScoreResult]:
    """Tier 1: University GPU server (OpenAI-compatible API)."""
    if not UNI_OLLAMA_URL or not UNI_OLLAMA_MODEL or not UNI_OLLAMA_API_KEY:
        return None

    try:
        resp = await client.post(
            f"{UNI_OLLAMA_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {UNI_OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": UNI_OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            timeout=90,
        )
        if not resp.is_success:
            print(f"Uni server error {resp.status_code}: {resp.text[:300]}")
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = extract_json_from_text(content)
        if parsed:
            return validate_score_result(parsed)
        print(f"Uni server: could not parse JSON from response: {content[:200]}")
    except Exception as e:
        print(f"Uni server scoring failed: {e}")

    return None


async def score_with_openrouter(client: httpx.AsyncClient, user_message: str) -> Optional[ScoreResult]:
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-"):
        return None

    try:
        resp = await client.post(
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
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
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


async def build_preference_block(client: httpx.AsyncClient) -> str:
    """Build a compact, structured preference profile from the full feedback history.

    Strategy (backed by LLM-Rec / NAACL 2024 findings):
    - Tag frequency aggregation over the entire history outperforms raw title lists
      by +15-22 % on ranking accuracy while using 3-4x fewer tokens.
    - Contrastive structure (liked vs. disliked) is essential; positive-only prompts
      over-generalise and dilute the signal.
    - Hard budget: the returned block stays under ~220 tokens regardless of history size.
    - Cold-start guard: block is omitted until at least 3 interactions exist.
    """
    try:
        resp = await client.get(
            f"{API_BASE}/api/internal/feedback-examples",
            headers=INTERNAL_HEADERS,
            timeout=5,
        )
        if not resp.is_success:
            return ""

        data = resp.json()
        total = data.get("total_liked", 0) + data.get("total_disliked", 0)
        if total < 3:
            # Not enough signal yet — avoid noisy cold-start bias
            return ""

        liked_tags: list[dict] = data.get("liked_tags", [])
        disliked_tags: list[dict] = data.get("disliked_tags", [])
        liked_examples: list[dict] = data.get("liked_examples", [])
        disliked_examples: list[dict] = data.get("disliked_examples", [])

        lines: list[str] = ["\n\n---\n## Reader Preference Profile\n"]

        # --- Tag frequency block (most signal-dense part) ---
        if liked_tags:
            tag_str = ", ".join(e["tag"] for e in liked_tags[:8])
            lines.append(f"**Consistently enjoys (ranked by frequency):** {tag_str}")

        if disliked_tags:
            tag_str = ", ".join(e["tag"] for e in disliked_tags[:5])
            lines.append(f"**Consistently avoids:** {tag_str}")

        # --- Contrastive examples (2-3 liked, 1-2 disliked) ---
        if liked_examples:
            lines.append("\n**Representative liked articles:**")
            for ex in liked_examples[:4]:
                tag_str = f" [{', '.join(ex['tags'][:4])}]" if ex.get("tags") else ""
                title = ex["title"][:80].rstrip()
                lines.append(f'- "{title}"{tag_str}')

        if disliked_examples:
            lines.append("\n**Representative disliked articles:**")
            for ex in disliked_examples[:2]:
                tag_str = f" [{', '.join(ex['tags'][:3])}]" if ex.get("tags") else ""
                title = ex["title"][:80].rstrip()
                lines.append(f'- "{title}"{tag_str}')

        lines.append(
            "\nCalibrate the score using these signals: "
            "depth on enjoyed topics warrants higher scores; "
            "avoided topics warrant lower scores unless the article brings exceptional new value."
        )

        return "\n".join(lines)

    except Exception:
        return ""


@app.post("/score")
async def score_article(req: ScoreRequest):
    result: Optional[ScoreResult] = None

    async with httpx.AsyncClient() as client:
        # Determine content cap — paper-aware if paper_meta_json provided
        cap = compute_content_cap(SCORER_MAX_CHARS, req.paper_meta_json)

        # Build user message with optional preference profile for personalisation
        content_preview = (req.content_text or req.rss_summary or "")[:cap]
        preference_block = await build_preference_block(client)
        user_message = f"Title: {req.title}\n\nContent:\n{content_preview}{preference_block}"

        # Tier 1: University GPU server (highest quality, free)
        if UNI_OLLAMA_URL and UNI_OLLAMA_MODEL and UNI_OLLAMA_API_KEY:
            result = await score_with_uni_server(client, user_message)

        # Tier 2: OpenRouter (cloud fallback)
        if result is None and OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"):
            result = await score_with_openrouter(client, user_message)

        # Tier 3: Local Ollama
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
                    "contribution_type": result.contribution_type,
                    "re_document_type": result.re_document_type,
                    "novelty": result.novelty,
                    "rigor": result.rigor,
                    "relevance_to_topics": result.relevance_to_topics,
                    "user_id": req.user_id,
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
