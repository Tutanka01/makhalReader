from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from prompt import JSON_RETRY_PROMPT, SYSTEM_PROMPT

app = FastAPI(title="MakhalReader Scorer")

SCORING_VERSION = 3

# Generic OpenAI-compatible endpoint (highest priority when set): point it at any
# OpenAI-compatible server (vLLM, llama.cpp, LM Studio, Groq, Together, OpenAI…).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_DISABLE_FALLBACK = os.getenv("LLM_DISABLE_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}

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


def provider_metadata(
    provider: str,
    model: str,
    *,
    response_model: Optional[str] = None,
    finish_reason: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict[str, str]:
    metadata = {
        "provider": provider,
        "provider_model": response_model or model or "unknown",
    }
    if model and response_model and response_model != model:
        metadata["provider_configured_model"] = model
    if finish_reason:
        metadata["provider_finish_reason"] = finish_reason
    if base_url:
        metadata["provider_base_url"] = base_url
    return metadata


def add_provider_metadata(result: ScoreResult, metadata: dict[str, str]) -> ScoreResult:
    result.score_details.update(metadata)
    return result


def normalize_llm_content(content: Any) -> Optional[str]:
    """Normalize common chat content shapes into text without raising."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "content"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        parts.append(value)
                        break
        text = "\n".join(part for part in parts if part.strip()).strip()
        return text or None
    return None


def parse_response_json(provider: str, resp: httpx.Response) -> Optional[dict]:
    try:
        data = resp.json()
    except Exception as e:
        print(f"{provider}: response was not valid JSON: {e}; body={resp.text[:300]}")
        return None
    if not isinstance(data, dict):
        print(f"{provider}: response JSON was not an object: {str(data)[:300]}")
        return None
    return data


def extract_openai_chat_content(data: dict, provider: str, configured_model: str = "") -> tuple[Optional[str], dict[str, str]]:
    response_model = data.get("model") if isinstance(data.get("model"), str) else None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        print(f"{provider}: malformed response without choices: {str(data)[:300]}")
        return None, provider_metadata(provider, configured_model, response_model=response_model)

    choice = choices[0]
    if not isinstance(choice, dict):
        print(f"{provider}: malformed first choice: {str(choice)[:300]}")
        return None, provider_metadata(provider, configured_model, response_model=response_model)

    finish_reason = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else choice.get("text")
    normalized = normalize_llm_content(content)
    metadata = provider_metadata(provider, configured_model, response_model=response_model, finish_reason=finish_reason)
    if normalized is None:
        print(f"{provider}: response content was not usable text: {str(content)[:300]}")
    return normalized, metadata


def extract_ollama_chat_content(data: dict) -> tuple[Optional[str], dict[str, str]]:
    response_model = data.get("model") if isinstance(data.get("model"), str) else OLLAMA_MODEL
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else data.get("response")
    normalized = normalize_llm_content(content)
    metadata = provider_metadata("Ollama", OLLAMA_MODEL, response_model=response_model)
    if normalized is None:
        print(f"Ollama: response content was not usable text: {str(content)[:300]}")
    return normalized, metadata


def build_retry_message(user_message: str, bad_content: str) -> str:
    clipped_bad_content = bad_content.strip()[:1800]
    return (
        f"{user_message}\n\n"
        "Previous malformed response to repair or replace:\n"
        f"{clipped_bad_content or '(empty response)'}"
    )


async def post_openai_chat(
    client: httpx.AsyncClient,
    *,
    provider: str,
    url: str,
    headers: dict[str, str],
    model: str,
    system_prompt: str,
    user_message: str,
    timeout: float,
) -> Optional[dict]:
    try:
        resp = await client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.0,
                "max_tokens": 1200,
            },
            timeout=timeout,
        )
    except Exception as e:
        print(f"{provider} scoring request failed: {e}")
        return None

    if not resp.is_success:
        print(f"{provider} error {resp.status_code}: {resp.text[:500]}")
        return None
    return parse_response_json(provider, resp)


async def score_openai_chat_provider(
    client: httpx.AsyncClient,
    *,
    provider: str,
    url: str,
    headers: dict[str, str],
    model: str,
    user_message: str,
    article_words: int,
    summary_words: int,
    timeout: float = 60,
    base_url: Optional[str] = None,
) -> Optional[ScoreResult]:
    data = await post_openai_chat(
        client,
        provider=provider,
        url=url,
        headers=headers,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        timeout=timeout,
    )
    if not data:
        return None

    content, metadata = extract_openai_chat_content(data, provider, model)
    if base_url:
        metadata["provider_base_url"] = base_url
    if not content:
        return None

    result = build_result_from_llm_content(provider, content, article_words, summary_words, metadata)
    if result is not None:
        return result

    retry_data = await post_openai_chat(
        client,
        provider=f"{provider} JSON retry",
        url=url,
        headers=headers,
        model=model,
        system_prompt=JSON_RETRY_PROMPT,
        user_message=build_retry_message(user_message, content),
        timeout=timeout,
    )
    if not retry_data:
        return None

    retry_content, retry_metadata = extract_openai_chat_content(retry_data, provider, model)
    if base_url:
        retry_metadata["provider_base_url"] = base_url
    retry_metadata["provider_retry"] = "json-only"
    if not retry_content:
        return None
    return build_result_from_llm_content(provider, retry_content, article_words, summary_words, retry_metadata)


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
    reading_lenses: list[str] = Field(default_factory=list)
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

    @field_validator("reading_lenses", mode="before")
    @classmethod
    def normalize_reading_lenses(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        allowed = {
            "latest",
            "opinion",
            "contrarian",
            "debate",
            "community-signal",
            "practical",
            "deep-dive",
            "weak-signal",
            "release-signal",
        }
        lenses: list[str] = []
        for item in value[:5]:
            lens = re.sub(r"[^a-z0-9._+-]+", "-", str(item).strip().lower()).strip("-")
            if lens in allowed and lens not in lenses:
                lenses.append(lens)
        return lenses

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

    candidates.extend(balanced_json_objects(text))

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def balanced_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    start: Optional[int] = None
    depth = 0
    in_string = False
    escape = False

    for idx, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : idx + 1].strip())
                start = None

    return objects


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
            "reading_lenses": data.get("reading_lenses", []),
            "tags": data.get("tags", []),
            "summary_bullets": data.get("summary_bullets", []),
            "reason": data.get("reason", "Legacy score-only response."),
        }
    return ScoreAnalysis.model_validate(data)


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def compute_final_score(analysis: ScoreAnalysis, article_words: int, summary_words: int) -> tuple[float, list[str], list[str]]:
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
    adjustments: list[str] = []

    practical_note = (
        analysis.content_type in {"opinion", "tutorial", "generic"}
        and analysis.topic_fit >= 2.0
        and analysis.operational_value >= 1.5
        and analysis.noise_penalty <= 1.2
        and analysis.confidence >= 0.65
    )

    if practical_note:
        score += 0.35
        adjustments.append("practical-note")
        if score < 6.2:
            score = 6.2
            adjustments.append("practical-floor")

    def cap(limit: float, reason: str) -> None:
        nonlocal score
        if score > limit:
            score = limit
            caps.append(reason)

    if analysis.topic_fit < 1.0 and analysis.strategic_value < 1.0:
        cap(4.0, "low-fit")
    if analysis.noise_penalty >= 2.5 and analysis.strategic_value < 2.5:
        cap(4.5, "high-noise")
    if analysis.content_type == "generic" and not practical_note:
        cap(4.8, "generic-content")
    if analysis.content_type == "opinion" and analysis.novelty < 2.2:
        cap(7.2 if practical_note else 6.0, "practical-opinion" if practical_note else "ordinary-opinion")
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

    return round(clamp(score, 0.0, 10.0), 1), caps, adjustments


def build_reason(analysis: ScoreAnalysis, score: float, caps: list[str], adjustments: list[str]) -> str:
    axis_note = (
        f"[{analysis.content_type}, conf={analysis.confidence:.2f}, "
        f"fit={analysis.topic_fit:.1f}, depth={analysis.technical_depth:.1f}, "
        f"ops={analysis.operational_value:.1f}, strat={analysis.strategic_value:.1f}, "
        f"novelty={analysis.novelty:.1f}, noise={analysis.noise_penalty:.1f}, score={score:.1f}]"
    )
    cap_note = f" Caps: {', '.join(caps)}." if caps else ""
    adjustment_note = f" Adjustments: {', '.join(adjustments)}." if adjustments else ""
    reason = analysis.reason or "Scored from structured relevance axes."
    return f"{reason} {axis_note}{cap_note}{adjustment_note}"[:500]


def build_result(analysis: ScoreAnalysis, article_words: int, summary_words: int) -> ScoreResult:
    score, caps, adjustments = compute_final_score(analysis, article_words, summary_words)
    details = {
        "topic_fit": analysis.topic_fit,
        "technical_depth": analysis.technical_depth,
        "operational_value": analysis.operational_value,
        "strategic_value": analysis.strategic_value,
        "novelty": analysis.novelty,
        "noise_penalty": analysis.noise_penalty,
        "confidence": analysis.confidence,
        "content_type": analysis.content_type,
        "reading_lenses": analysis.reading_lenses,
        "article_words": article_words,
        "summary_words": summary_words,
        "caps": caps,
        "adjustments": adjustments,
        "scoring_version": SCORING_VERSION,
    }
    return ScoreResult(
        score=score,
        tags=analysis.tags,
        summary_bullets=analysis.summary_bullets,
        reason=build_reason(analysis, score, caps, adjustments),
        score_details=details,
    )


def build_result_from_llm_content(
    provider: str,
    content: str,
    article_words: int,
    summary_words: int,
    metadata: Optional[dict[str, str]] = None,
) -> Optional[ScoreResult]:
    parsed = extract_json_from_text(content)
    if not parsed:
        print(f"{provider}: could not parse JSON from response: {content[:300]}")
        return None

    try:
        result = build_result(validate_analysis(parsed), article_words, summary_words)
        if metadata:
            add_provider_metadata(result, metadata)
        return result
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

    return await score_openai_chat_provider(
        client,
        provider="OpenAI-compatible",
        url=_chat_completions_url(LLM_BASE_URL),
        headers=headers,
        model=LLM_MODEL,
        user_message=user_message,
        article_words=article_words,
        summary_words=summary_words,
        timeout=60,
        base_url=LLM_BASE_URL,
    )


async def score_with_openrouter(
    client: httpx.AsyncClient,
    user_message: str,
    article_words: int,
    summary_words: int,
) -> Optional[ScoreResult]:
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-"):
        return None

    return await score_openai_chat_provider(
        client,
        provider="OpenRouter",
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/makhalreader",
            "X-Title": "MakhalReader",
        },
        model=SCORER_MODEL,
        user_message=user_message,
        article_words=article_words,
        summary_words=summary_words,
        timeout=60,
    )


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
        data = parse_response_json("Ollama", resp)
        if not data:
            return None
        content, metadata = extract_ollama_chat_content(data)
        if not content:
            return None
        result = build_result_from_llm_content("Ollama", content, article_words, summary_words, metadata)
        if result is not None:
            return result

        retry_resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": JSON_RETRY_PROMPT},
                    {"role": "user", "content": build_retry_message(user_message, content)},
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
        if not retry_resp.is_success:
            print(f"Ollama JSON retry error {retry_resp.status_code}: {retry_resp.text[:300]}")
            return None
        retry_data = parse_response_json("Ollama JSON retry", retry_resp)
        if not retry_data:
            return None
        retry_content, retry_metadata = extract_ollama_chat_content(retry_data)
        retry_metadata["provider_retry"] = "json-only"
        if not retry_content:
            return None
        return build_result_from_llm_content(
            "Ollama",
            retry_content,
            article_words,
            summary_words,
            retry_metadata,
        )
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
            result = await score_with_openai_compatible(client, user_message, article_words, summary_words)

        if result is None and not (LLM_BASE_URL and LLM_DISABLE_FALLBACK):
            if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"):
                result = await score_with_openrouter(client, user_message, article_words, summary_words)

            if result is None:
                result = await score_with_ollama(client, user_message, article_words, summary_words)
        elif result is None:
            print("Scoring fallback disabled by LLM_DISABLE_FALLBACK after LLM_BASE_URL failure.")

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
    return {
        "status": "ok",
        "scoring_version": SCORING_VERSION,
        "llm_fallback_disabled": LLM_DISABLE_FALLBACK,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
