import asyncio
import json
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth import require_session
from database import Article, get_db
from models import AskRequest

router = APIRouter()
_auth = Depends(require_session)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
QA_MODEL = os.getenv("QA_MODEL", os.getenv("SCORER_MODEL", "google/gemini-flash-1.5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host-gateway:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Semaphore to prevent concurrent LLM ask calls (cost protection)
_ask_semaphore = asyncio.Semaphore(2)


@router.post("/api/articles/{article_id}/ask")
async def ask_article(
    article_id: int,
    body: AskRequest,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    context = (article.content_text or "").strip()
    if not context and article.content_html:
        context = re.sub(r"<[^>]+>", " ", article.content_html)
        context = re.sub(r"\s+", " ", context).strip()
    context = context[:6000]

    system_prompt = (
        "You are an expert reading assistant. The user is reading the article below and asks you questions about it.\n\n"
        "Guidelines:\n"
        "- Answer using ONLY information present in the article — never invent or assume anything.\n"
        "- Detect the language of the user's question and reply in that exact language.\n"
        "- Respond in the most natural way for the question: flowing prose for open questions, "
        "a list only when the question genuinely calls for enumeration, a direct quote when the user "
        "wants a specific passage. Let the question shape the format — never impose one.\n"
        "- Be concise and direct. No greetings, no filler, no meta-commentary.\n"
        "- Use Markdown sparingly: **bold** for key terms, > for quoting the article directly.\n"
        "- If the information is not in the article, say so in one sentence without speculating.\n\n"
        f"Article — {article.title}\n\n{context}"
    )

    async def generate():
        async with _ask_semaphore:
            use_openrouter = bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"))
            try:
                if use_openrouter:
                    async with httpx.AsyncClient(timeout=60) as client:
                        async with client.stream(
                            "POST",
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": QA_MODEL,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": body.question},
                                ],
                                "stream": True,
                                "max_tokens": 1024,
                                "temperature": 0.3,
                            },
                        ) as resp:
                            async for line in resp.aiter_lines():
                                if not line.startswith("data: "):
                                    continue
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk["choices"][0]["delta"].get("content", "")
                                    if delta:
                                        yield f"data: {json.dumps({'text': delta})}\n\n"
                                except Exception:
                                    pass
                else:
                    async with httpx.AsyncClient(timeout=60) as client:
                        async with client.stream(
                            "POST",
                            f"{OLLAMA_URL}/api/chat",
                            json={
                                "model": OLLAMA_MODEL,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": body.question},
                                ],
                                "stream": True,
                                "options": {"temperature": 0.3, "num_predict": 1024},
                            },
                        ) as resp:
                            async for line in resp.aiter_lines():
                                if not line.strip():
                                    continue
                                try:
                                    chunk = json.loads(line)
                                    delta = chunk.get("message", {}).get("content", "")
                                    if delta:
                                        yield f"data: {json.dumps({'text': delta})}\n\n"
                                    if chunk.get("done"):
                                        break
                                except Exception:
                                    pass
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
