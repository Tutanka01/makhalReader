import asyncio
import json
import re
from typing import List, Optional
from urllib.parse import quote_plus, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="MakhalReader Extractor")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class ExtractRequest(BaseModel):
    url: str
    rss_title: str = ""
    rss_summary: str = ""


class ExtractResponse(BaseModel):
    title: str
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images: List[str] = []
    author: Optional[str] = None
    read_time_minutes: int = 1
    extraction_failed: bool = False


def extract_images_from_html(html: str, base_url: str, max_images: int = 10) -> List[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for img in soup.find_all("img", src=True):
            src = img.get("src", "").strip()
            if not src or src.startswith("data:"):
                continue
            if src.startswith("//"):
                parsed = urlparse(base_url)
                src = f"{parsed.scheme}:{src}"
            elif src.startswith("/"):
                parsed = urlparse(base_url)
                src = f"{parsed.scheme}://{parsed.netloc}{src}"
            elif not src.startswith("http"):
                continue
            images.append(src)
            if len(images) >= max_images:
                break
        return images
    except Exception:
        return []


def estimate_read_time(text: str) -> int:
    if not text:
        return 1
    words = len(text.split())
    minutes = max(1, round(words / 200))
    return minutes


def trafilatura_extract(html: str, url: str) -> dict:
    try:
        result_json = trafilatura.extract(
            html,
            url=url,
            include_images=True,
            output_format="json",
            favor_recall=True,
            include_comments=False,
            include_tables=True,
        )
        if result_json:
            data = json.loads(result_json)
            return {
                "title": data.get("title"),
                "text": data.get("text"),
                "author": data.get("author"),
                "raw_html": trafilatura.extract(
                    html,
                    url=url,
                    include_images=True,
                    output_format="html",
                    favor_recall=True,
                ),
            }
    except Exception:
        pass
    return {"title": None, "text": None, "author": None, "raw_html": None}


async def fetch_url(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


async def try_google_cache(client: httpx.AsyncClient, url: str) -> Optional[str]:
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{quote_plus(url)}"
    return await fetch_url(client, cache_url)


async def try_wayback_machine(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        api_url = f"https://archive.org/wayback/available?url={quote_plus(url)}"
        resp = await client.get(api_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            snapshot_url = data.get("archived_snapshots", {}).get("closest", {}).get("url")
            if snapshot_url:
                return await fetch_url(client, snapshot_url)
    except Exception:
        pass
    return None


@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest) -> ExtractResponse:
    async with httpx.AsyncClient() as client:
        html = await fetch_url(client, req.url)
        content_text = None
        content_html = None
        title = req.rss_title
        author = None
        images = []

        if html:
            extracted = trafilatura_extract(html, req.url)
            content_text = extracted.get("text")
            content_html = extracted.get("raw_html")
            if extracted.get("title"):
                title = extracted["title"]
            author = extracted.get("author")
            if html:
                images = extract_images_from_html(html, req.url)

        # Strategy 2: try Google cache if content too short
        if not content_text or len(content_text) < 500:
            cache_html = await try_google_cache(client, req.url)
            if cache_html:
                extracted = trafilatura_extract(cache_html, req.url)
                if extracted.get("text") and len(extracted["text"]) >= len(content_text or ""):
                    content_text = extracted["text"]
                    content_html = extracted.get("raw_html")
                    if extracted.get("title"):
                        title = extracted["title"]
                    if extracted.get("author"):
                        author = extracted["author"]
                    if not images:
                        images = extract_images_from_html(cache_html, req.url)

        # Strategy 3: try Wayback Machine
        if not content_text or len(content_text) < 500:
            wb_html = await try_wayback_machine(client, req.url)
            if wb_html:
                extracted = trafilatura_extract(wb_html, req.url)
                if extracted.get("text") and len(extracted["text"]) >= len(content_text or ""):
                    content_text = extracted["text"]
                    content_html = extracted.get("raw_html")
                    if extracted.get("title"):
                        title = extracted["title"]
                    if extracted.get("author"):
                        author = extracted["author"]
                    if not images:
                        images = extract_images_from_html(wb_html, req.url)

        extraction_failed = False

        # Fallback: use RSS summary
        if not content_text or len(content_text) < 100:
            content_text = req.rss_summary
            extraction_failed = True

        read_time = estimate_read_time(content_text or "")

        return ExtractResponse(
            title=title or req.rss_title,
            content_html=content_html,
            content_text=content_text,
            images=images[:10],
            author=author,
            read_time_minutes=read_time,
            extraction_failed=extraction_failed,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
