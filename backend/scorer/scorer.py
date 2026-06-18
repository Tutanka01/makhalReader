import json
import os
import re
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from prompt import SYSTEM_PROMPT

app = FastAPI(title="MakhalReader Scorer")

# Generic OpenAI-compatible endpoint (highest priority when set): point it at any
# OpenAI-compatible server (vLLM, llama.cpp, LM Studio, Groq, Together, OpenAI…).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SCORER_MODEL = os.getenv("SCORER_MODEL", "google/gemini-flash-1.5")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
API_BASE = "http://api:8000"


def _chat_completions_url(base: str) -> str:
    """Build the chat-completions URL from a base, forgiving about how it's written."""
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"
API_SECRET = os.getenv("API_SECRET", "changeme")

INTERNAL_HEADERS = {"X-Internal-Secret": API_SECRET, "Content-Type": "application/json"}

CONTENT_TYPES = {"postmortem", "tutorial", "paper", "release", "opinion", "news", "generic"}
AXIS_FIELDS = {
    "topic_fit",
    "technical_depth",
    "operational_value",
    "strategic_value",
    "novelty",
    "noise_penalty",
}
NUMERIC_FIELDS = AXIS_FIELDS | {"confidence"}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ScoreRequest(BaseModel):
    article_id: int
    title: str
    content_text: str
    rss_summary: str = ""


class ScoreAnalysis(BaseModel):
    topic_fit: float = Field(ge=0.0, le=3.0)
    technical_depth: float = Field(ge=0.0, le=3.0)
    operational_value: float = Field(ge=0.0, le=3.0)
    strategic_value: float = Field(ge=0.0, le=3.0)
    novelty: float = Field(ge=0.0, le=3.0)
    noise_penalty: float = Field(ge=0.0, le=3.0)
    confidence: float = Field(ge=0.0, le=1.0)
    content_type: str
    tags: list[str] = Field(default_factory=list)
    summary_bullets: list[str] = Field(default_factory=list)
    reason: str = ""

    @field_validator(
        "topic_fit",
        "technical_depth",
        "operational_value",
        "strategic_value",
        "novelty",
        "noise_penalty",
        mode="before",
    )
    @classmethod
    def normalize_axis(cls, value: Any) -> float:
        try:
            return clamp(float(value), 0.0, 3.0)
        except (TypeError, ValueError):
            return 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> float:
        try:
            return clamp(float(value), 0.0, 1.0)
        except (TypeError, ValueError):
            return 0.2

    @field_validator("content_type")
    @classmethod
    def normalize_content_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in CONTENT_TYPES else "generic"

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        tags: list[str] = []
        for item in value[:5]:
            tag = re.sub(r"[^a-z0-9._+-]+", "-", str(item).strip().lower()).strip("-")
            if tag and tag not in tags:
                tags.append(tag[:40])
        return tags

    @field_validator("summary_bullets", mode="before")
    @classmethod
    def normalize_summary(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:220] for item in value[:3] if str(item).strip()]

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return str(value or "").strip()[:350]


class ScoreResult(BaseModel):
    score: float
    tags: list[str] = Field(default_factory=list)
    summary_bullets: list[str] = Field(default_factory=list)
    reason: str = ""
    score_details: dict[str, Any] = Field(default_factory=dict)


def repair_json_text(text: str) -> str:
    """Repair common LLM JSON glitches without changing valid JSON."""
    repaired = text.strip()
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    for field in NUMERIC_FIELDS:
        # Example seen in production: "strategic_value": IE 0.5
        repaired = re.sub(
            rf'("{field}"\s*:\s*)[A-Za-z_][A-Za-z0-9_-]*\s+(-?\d+(?:\.\d+)?)',
            rf"\1\2",
            repaired,
        )
    return repaired


def json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\{[\s\S]*\}",
    ]
    for pattern in patterns:
        candidates.extend(match.strip() for match in re.findall(pattern, text, re.DOTALL))

    first_brace = text.find("{")
    if first_brace >= 0:
        last_brace = text.rfind("}")
        if last_brace > first_brace:
            candidates.append(text[first_brace : last_brace + 1].strip())
        else:
            candidates.append(text[first_brace:].strip())

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def extract_partial_analysis(text: str) -> Optional[dict]:
    """Recover a conservative analysis from a truncated or slightly invalid JSON object."""
    data: dict[str, Any] = {}
    found_numeric = 0
    for field in NUMERIC_FIELDS:
        match = re.search(
            rf'"{field}"\s*:\s*(?:[A-Za-z_][A-Za-z0-9_-]*\s+)?(-?\d+(?:\.\d+)?)',
            text,
            re.IGNORECASE,
        )
        if match:
            found_numeric += 1
            data[field] = float(match.group(1))

    if found_numeric < 4:
        return None

    type_match = re.search(r'"content_type"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
    data["content_type"] = type_match.group(1) if type_match else "generic"

    for field in AXIS_FIELDS - {"noise_penalty"}:
        data.setdefault(field, 0.0)
    data.setdefault("noise_penalty", 2.5)
    data["confidence"] = min(float(data.get("confidence", 0.2)), 0.35)
    data.setdefault("tags", [])
    data.setdefault("summary_bullets", [])
    data.setdefault("reason", "Recovered from malformed LLM JSON.")
    return data


def extract_json_from_text(text: str) -> Optional[dict]:
    """Extract JSON from text, handling markdown, minor glitches, and truncation."""
    for candidate in json_candidates(text):
        for maybe_repaired in (candidate, repair_json_text(candidate)):
            try:
                parsed = json.loads(maybe_repaired)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    return extract_partial_analysis(text)


def validate_analysis(data: dict) -> ScoreAnalysis:
    # Backward compatibility: an old model response with only "score" still works,
    # but it is converted into a low-confidence generic analysis.
    if "score" in data and "topic_fit" not in data:
        raw_score = clamp(float(data.get("score", 0.0)), 0.0, 10.0)
        axis = clamp(raw_score / 10.0 * 3.0, 0.0, 3.0)
        data = {
            "topic_fit": axis,
            "technical_depth": axis * 0.7,
            "operational_value": axis * 0.7,
            "strategic_value": axis * 0.4,
            "novelty": axis * 0.5,
            "noise_penalty": max(0.0, 3.0 - axis),
            "confidence": 0.35,
            "content_type": "generic",
            "tags": data.get("tags", []),
            "summary_bullets": data.get("summary_bullets", []),
            "reason": data.get("reason", "Legacy score-only response."),
        }
    return ScoreAnalysis.model_validate(data)


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def compute_final_score(analysis: ScoreAnalysis, article_words: int, summary_words: int) -> tuple[float, list[str]]:
    """Convert LLM analysis axes into a stable 0-10 score.

    The LLM identifies evidence; this function owns calibration. That makes
    scoring easier to test and much less sensitive to prompt drift.
    """
    weighted_positive = (
        analysis.topic_fit * 2.4
        + analysis.technical_depth * 1.7
        + analysis.operational_value * 1.8
        + analysis.strategic_value * 1.1
        + analysis.novelty * 1.2
    )
    max_positive = 3.0 * (2.4 + 1.7 + 1.8 + 1.1 + 1.2)
    score = weighted_positive / max_positive * 10.0
    score -= analysis.noise_penalty * 1.15

    # Content-type priors. They are intentionally small; axes still dominate.
    if analysis.content_type == "postmortem" and analysis.operational_value >= 2.0:
        score += 0.45
    elif analysis.content_type == "paper" and (analysis.technical_depth >= 2.2 or analysis.operational_value >= 2.0):
        score += 0.25
    elif analysis.content_type == "release" and max(analysis.operational_value, analysis.strategic_value, analysis.novelty) >= 2.3:
        score += 0.25
    elif analysis.content_type == "generic":
        score -= 0.35

    # Low confidence should reduce extremes, not flatten all useful signals.
    confidence_factor = 0.70 + (0.30 * analysis.confidence)
    score = 4.8 + ((score - 4.8) * confidence_factor)

    caps: list[str] = []

    def cap(limit: float, reason: str) -> None:
        nonlocal score
        if score > limit:
            score = limit
            caps.append(reason)

    if analysis.topic_fit < 1.0 and analysis.strategic_value < 1.0:
        cap(4.0, "low-fit")
    if analysis.noise_penalty >= 2.5 and analysis.strategic_value < 2.5:
        cap(4.5, "high-noise")
    if analysis.content_type == "generic":
        cap(4.8, "generic-content")
    if analysis.content_type == "opinion" and analysis.novelty < 2.2:
        cap(6.0, "ordinary-opinion")
    if analysis.content_type == "tutorial" and analysis.technical_depth < 2.4 and analysis.operational_value < 2.2:
        cap(7.0, "routine-tutorial")
    if analysis.content_type in {"release", "news"} and max(
        analysis.operational_value, analysis.strategic_value, analysis.novelty
    ) < 2.2:
        cap(6.5, "limited-announcement")

    has_article_body = article_words >= 120
    has_any_context = article_words >= 40 or summary_words >= 30
    if not has_any_context:
        cap(5.0, "insufficient-context")
    elif not has_article_body and analysis.content_type not in {"release", "news"}:
        cap(5.8, "thin-extraction")

    if analysis.confidence < 0.35:
        cap(5.5, "very-low-confidence")
    elif analysis.confidence < 0.55:
        cap(7.0, "low-confidence")

    return round(clamp(score, 0.0, 10.0), 1), caps


def build_reason(analysis: ScoreAnalysis, score: float, caps: list[str]) -> str:
    axis_note = (
        f"[{analysis.content_type}, conf={analysis.confidence:.2f}, "
        f"fit={analysis.topic_fit:.1f}, depth={analysis.technical_depth:.1f}, "
        f"ops={analysis.operational_value:.1f}, strat={analysis.strategic_value:.1f}, "
        f"novelty={analysis.novelty:.1f}, noise={analysis.noise_penalty:.1f}, score={score:.1f}]"
    )
    cap_note = f" Caps: {', '.join(caps)}." if caps else ""
    reason = analysis.reason or "Scored from structured relevance axes."
    return f"{reason} {axis_note}{cap_note}"[:500]


def build_result(analysis: ScoreAnalysis, article_words: int, summary_words: int) -> ScoreResult:
    score, caps = compute_final_score(analysis, article_words, summary_words)
    details = {
        "topic_fit": analysis.topic_fit,
        "technical_depth": analysis.technical_depth,
        "operational_value": analysis.operational_value,
        "strategic_value": analysis.strategic_value,
        "novelty": analysis.novelty,
        "noise_penalty": analysis.noise_penalty,
        "confidence": analysis.confidence,
        "content_type": analysis.content_type,
        "article_words": article_words,
        "summary_words": summary_words,
        "caps": caps,
        "scoring_version": 2,
    }
    return ScoreResult(
        score=score,
        tags=analysis.tags,
        summary_bullets=analysis.summary_bullets,
        reason=build_reason(analysis, score, caps),
        score_details=details,
    )


def build_result_from_llm_content(
    provider: str,
    content: str,
    article_words: int,
    summary_words: int,
) -> Optional[ScoreResult]:
    parsed = extract_json_from_text(content)
    if not parsed:
        print(f"{provider}: could not parse JSON from response: {content[:300]}")
        return None

    try:
        return build_result(validate_analysis(parsed), article_words, summary_words)
    except Exception as e:
        print(f"{provider}: invalid score payload after JSON parse: {e}; response={content[:300]}")
        return None


async def score_with_openai_compatible(
    client: httpx.AsyncClient,
    user_message: str,
    article_words: int,
    summary_words: int,
) -> Optional[ScoreResult]:
    """Score via a generic OpenAI-compatible endpoint (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL)."""
    if not LLM_BASE_URL:
        return None

    headers = {"Content-Type": "application/json", "X-Title": "MakhalReader"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    try:
        resp = await client.post(
            _chat_completions_url(LLM_BASE_URL),
            headers=headers,
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.0,
                "max_tokens": 1200,
            },
            timeout=60,
        )
        if not resp.is_success:
            print(f"OpenAI-compatible endpoint error {resp.status_code}: {resp.text[:500]}")
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return build_result_from_llm_content("OpenAI-compatible", content, article_words, summary_words)
    except Exception as e:
        print(f"OpenAI-compatible scoring failed: {e}")

    return None


async def score_with_openrouter(
    client: httpx.AsyncClient,
    user_message: str,
    article_words: int,
    summary_words: int,
) -> Optional[ScoreResult]:
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
                "temperature": 0.0,
                "max_tokens": 1200,
            },
            timeout=60,
        )
        if not resp.is_success:
            print(f"OpenRouter error {resp.status_code}: {resp.text[:500]}")
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return build_result_from_llm_content("OpenRouter", content, article_words, summary_words)
    except Exception as e:
        print(f"OpenRouter scoring failed: {e}")

    return None


async def score_with_ollama(
    client: httpx.AsyncClient,
    user_message: str,
    article_words: int,
    summary_words: int,
) -> Optional[ScoreResult]:
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
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 900,
                },
            },
            timeout=120,
        )
        if not resp.is_success:
            print(f"Ollama error {resp.status_code}: {resp.text[:300]}")
            return None
        data = resp.json()
        content = data["message"]["content"]
        return build_result_from_llm_content("Ollama", content, article_words, summary_words)
    except Exception as e:
        print(f"Ollama scoring failed: {e}")

    return None


async def build_preference_block(client: httpx.AsyncClient) -> str:
    """Build a compact preference profile from explicit and implicit history."""
    try:
        resp = await client.get(
            f"{API_BASE}/api/internal/feedback-examples",
            headers=INTERNAL_HEADERS,
            timeout=5,
        )
        if not resp.is_success:
            return ""

        data = resp.json()
        total = (
            data.get("total_liked", 0)
            + data.get("total_disliked", 0)
            + data.get("total_bookmarked", 0)
            + data.get("total_read", 0)
        )
        if total < 3:
            return ""

        liked_tags: list[dict] = data.get("liked_tags", [])
        disliked_tags: list[dict] = data.get("disliked_tags", [])
        bookmarked_tags: list[dict] = data.get("bookmarked_tags", [])
        read_tags: list[dict] = data.get("read_tags", [])
        liked_examples: list[dict] = data.get("liked_examples", [])
        disliked_examples: list[dict] = data.get("disliked_examples", [])

        lines: list[str] = ["\n\n## Preference profile"]
        if liked_tags:
            lines.append("likes: " + ", ".join(e["tag"] for e in liked_tags[:7]))
        if disliked_tags:
            lines.append("avoid unless exceptional: " + ", ".join(e["tag"] for e in disliked_tags[:5]))
        if bookmarked_tags:
            lines.append("bookmarks: " + ", ".join(e["tag"] for e in bookmarked_tags[:5]))
        if read_tags:
            lines.append("read history: " + ", ".join(e["tag"] for e in read_tags[:5]))

        if liked_examples:
            examples = "; ".join(f'"{ex["title"][:70].rstrip()}"' for ex in liked_examples[:2])
            lines.append(f"liked examples: {examples}")
        if disliked_examples:
            examples = "; ".join(f'"{ex["title"][:70].rstrip()}"' for ex in disliked_examples[:2])
            lines.append(f"disliked examples: {examples}")

        lines.append("Use as a prior only; weak content must stay weak.")
        return "\n".join(lines)

    except Exception:
        return ""


def build_user_message(req: ScoreRequest, preference_block: str) -> tuple[str, int, int]:
    content_preview = (req.content_text or "").strip()[:4500]
    summary_preview = (req.rss_summary or "").strip()[:900]
    article_words = word_count(content_preview)
    summary_words = word_count(summary_preview)
    user_message = (
        f"Title: {req.title.strip()[:300]}\n"
        f"Article word count in provided text: {article_words}\n"
        f"RSS summary word count: {summary_words}\n\n"
        f"RSS summary:\n{summary_preview or '(none)'}\n\n"
        f"Article text:\n{content_preview or '(no extracted article text)'}"
        f"{preference_block}"
    )
    return user_message, article_words, summary_words


@app.post("/score")
async def score_article(req: ScoreRequest):
    result: Optional[ScoreResult] = None

    async with httpx.AsyncClient() as client:
        preference_block = await build_preference_block(client)
        user_message, article_words, summary_words = build_user_message(req, preference_block)

        if LLM_BASE_URL:
            # Explicit OpenAI-compatible endpoint — used exclusively, no fallback.
            result = await score_with_openai_compatible(client, user_message, article_words, summary_words)
        else:
            if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"):
                result = await score_with_openrouter(client, user_message, article_words, summary_words)

            if result is None:
                result = await score_with_ollama(client, user_message, article_words, summary_words)

        if result is None:
            raise HTTPException(
                status_code=503,
                detail="Scoring failed: unable to reach any LLM service or parse a valid score.",
            )

        try:
            resp = await client.post(
                f"{API_BASE}/api/internal/articles/{req.article_id}/score",
                json={
                    "score": result.score,
                    "tags": result.tags,
                    "summary_bullets": result.summary_bullets,
                    "reason": result.reason,
                    "score_details": result.score_details,
                },
                headers=INTERNAL_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"Failed to post score to API: {e}")
            raise

    return {"status": "ok", "score": result.score, "score_details": result.score_details}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
