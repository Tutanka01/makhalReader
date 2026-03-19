import asyncio
import json
import re
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup, Tag
from fastapi import FastAPI
from pydantic import BaseModel
from readability import Document

app = FastAPI(title="MakhalReader Extractor")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

MIN_CONTENT_LENGTH = 300


class ExtractRequest(BaseModel):
    url: str
    rss_title: str = ""
    rss_summary: str = ""
    rss_content: str = ""  # full content:encoded HTML from the feed (often complete article)


class ExtractResponse(BaseModel):
    title: str
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images: List[str] = []
    author: Optional[str] = None
    read_time_minutes: int = 1
    extraction_failed: bool = False


# ---------------------------------------------------------------------------
# Content validation
# ---------------------------------------------------------------------------

def is_html_content_type(content_type: str) -> bool:
    """Accept only HTML/XHTML responses."""
    ct = content_type.lower().split(";")[0].strip()
    return ct in ("text/html", "application/xhtml+xml", "text/xml", "application/xml")


def is_garbled(text: str) -> bool:
    """
    Detect binary/mis-decoded content.
    A healthy HTML page should have >85% printable ASCII + common Unicode.
    If replacement chars (U+FFFD) or control chars dominate → garbled.
    """
    if not text or len(text) < 50:
        return False
    sample = text[:2000]
    bad = sum(
        1 for c in sample
        if c == "\ufffd"                       # UTF-8 replacement char
        or (ord(c) < 32 and c not in "\t\n\r") # control chars except whitespace
    )
    return (bad / len(sample)) > 0.04  # >4% bad chars → garbled


# ---------------------------------------------------------------------------
# HTML utilities
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    try:
        return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)
    except Exception:
        return text


def text_to_html(text: str) -> str:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)


def html_to_text(html: str) -> str:
    try:
        return BeautifulSoup(html, "html.parser").get_text(separator="\n\n", strip=True)
    except Exception:
        return ""


def clean_readability_html(raw: str, base_url: str) -> str:
    """Resolve relative URLs and remove readability's outer wrapper div."""
    try:
        soup = BeautifulSoup(raw, "html.parser")
        parsed_base = urlparse(base_url)

        for tag in soup.find_all(True):
            for attr in ("src", "href"):
                val = tag.get(attr, "")
                if not val:
                    continue
                if val.startswith("//"):
                    tag[attr] = f"{parsed_base.scheme}:{val}"
                elif val.startswith("/") and not val.startswith("//"):
                    tag[attr] = f"{parsed_base.scheme}://{parsed_base.netloc}{val}"

        # Remove empty paragraphs
        for p in soup.find_all("p"):
            if not p.get_text(strip=True) and not p.find("img"):
                p.decompose()

        # Unwrap outer readability div
        outer = soup.find("div", id=re.compile(r"readability"))
        if outer and isinstance(outer, Tag):
            return outer.decode_contents()

        return str(soup)
    except Exception:
        return raw


def extract_images_from_html(html: str, base_url: str, max_images: int = 10) -> List[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        images = []
        parsed = urlparse(base_url)
        for img in soup.find_all("img", src=True):
            src = img.get("src", "").strip()
            if not src or src.startswith("data:"):
                continue
            if src.startswith("//"):
                src = f"{parsed.scheme}:{src}"
            elif src.startswith("/"):
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
    return max(1, round(len(text.split()) / 200)) if text else 1


def clean_title(title: Optional[str]) -> Optional[str]:
    """Strip site suffixes like ' | Cloudflare Blog', ' - The New Stack', etc."""
    if not title:
        return None
    # Remove common site-name suffixes
    title = re.sub(r"\s*[\|\-–—]\s*[^|\-–—]{3,60}$", "", title).strip()
    # Collapse whitespace
    title = re.sub(r"\s+", " ", title).strip()
    return title if len(title) >= 4 else None


# ---------------------------------------------------------------------------
# Extraction strategies
# ---------------------------------------------------------------------------

def extract_with_readability(html: str, url: str) -> dict:
    """Primary — Mozilla Readability algorithm (Firefox Reader View)."""
    try:
        doc = Document(html, url=url)
        raw = doc.summary(html_partial=True)
        if not raw:
            return {}

        content_html = clean_readability_html(raw, url)
        content_text = html_to_text(content_html)

        if len(content_text) < MIN_CONTENT_LENGTH:
            return {}

        title = clean_title(doc.short_title()) or clean_title(doc.title())
        return {
            "title": title,
            "text": content_text,
            "author": None,
            "raw_html": content_html,
        }
    except Exception:
        return {}


def extract_with_trafilatura(html: str, url: str) -> dict:
    """Fallback — trafilatura (better precision on tricky sites)."""
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
        if not result_json:
            return {}

        data = json.loads(result_json)
        plain_text = data.get("text") or ""
        if len(plain_text) < MIN_CONTENT_LENGTH:
            return {}

        raw_html = trafilatura.extract(
            html,
            url=url,
            include_images=True,
            output_format="html",
            favor_recall=True,
        ) or text_to_html(plain_text)

        return {
            "title": clean_title(data.get("title")),
            "text": plain_text,
            "author": data.get("author"),
            "raw_html": raw_html,
        }
    except Exception:
        return {}


def best_extraction(html: str, url: str) -> dict:
    """
    Run both extractors, prefer readability (better HTML structure).
    Fall back to trafilatura if readability gives too little content.
    """
    r = extract_with_readability(html, url)
    t = extract_with_trafilatura(html, url)

    r_len = len(r.get("text") or "")
    t_len = len(t.get("text") or "")

    if not r and not t:
        return {}

    # Prefer readability unless trafilatura got >25% more content
    if r_len > 0 and r_len >= t_len * 0.75:
        result = r
        # Supplement with trafilatura's author if readability has none
        if not result.get("author") and t.get("author"):
            result["author"] = t["author"]
    elif t_len >= MIN_CONTENT_LENGTH:
        result = t
    else:
        result = r if r else t

    return result


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def fetch_url(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """
    Fetch URL and return HTML text, or None if:
    - non-200 response
    - non-HTML content type
    - garbled / binary content
    """
    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
        if resp.status_code != 200:
            return None

        content_type = resp.headers.get("content-type", "text/html")
        if not is_html_content_type(content_type):
            return None

        # Use detected encoding; fall back to apparent_encoding via httpx
        text = resp.text
        if is_garbled(text):
            # Try re-decoding with latin-1 as last resort
            try:
                text = resp.content.decode("latin-1")
            except Exception:
                return None
            if is_garbled(text):
                return None

        return text
    except Exception:
        return None


async def try_google_cache(client: httpx.AsyncClient, url: str) -> Optional[str]:
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{quote_plus(url)}"
    return await fetch_url(client, cache_url)


async def try_wayback_machine(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        resp = await client.get(
            f"https://archive.org/wayback/available?url={quote_plus(url)}", timeout=10
        )
        if resp.status_code == 200:
            snapshot_url = resp.json().get("archived_snapshots", {}).get("closest", {}).get("url")
            if snapshot_url:
                return await fetch_url(client, snapshot_url)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Title resolution — never return [no-title]
# ---------------------------------------------------------------------------

def resolve_title(
    extracted_title: Optional[str],
    rss_title: str,
    content_text: Optional[str],
) -> str:
    """
    Title priority:
    1. Cleaned title from extractor (if non-trivial)
    2. RSS feed title (most reliable — written by the author)
    3. First sentence of content
    4. "Untitled article" as last resort (never [no-title])
    """
    # 1. Extractor title
    if extracted_title and len(extracted_title) >= 5:
        return extracted_title

    # 2. RSS title
    rss = (rss_title or "").strip()
    if rss:
        return rss

    # 3. First sentence of content
    if content_text:
        first = content_text.strip().split("\n")[0][:120].strip()
        if len(first) >= 10:
            return first + ("…" if len(content_text.strip().split("\n")[0]) > 120 else "")

    return "Untitled article"


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest) -> ExtractResponse:
    async with httpx.AsyncClient() as client:
        content_text: Optional[str] = None
        content_html: Optional[str] = None
        extracted_title: Optional[str] = None
        author: Optional[str] = None
        images: List[str] = []

        # ── Strategy 1: direct fetch ──────────────────────────────────────
        html = await fetch_url(client, req.url)
        if html:
            extracted = best_extraction(html, req.url)
            content_text = extracted.get("text")
            content_html = extracted.get("raw_html")
            extracted_title = extracted.get("title")
            author = extracted.get("author")
            images = extract_images_from_html(html, req.url)

        # ── Strategy 2: Google cache ──────────────────────────────────────
        if not content_text or len(content_text) < MIN_CONTENT_LENGTH:
            cache_html = await try_google_cache(client, req.url)
            if cache_html:
                extracted = best_extraction(cache_html, req.url)
                if len(extracted.get("text") or "") > len(content_text or ""):
                    content_text = extracted.get("text")
                    content_html = extracted.get("raw_html")
                    if extracted.get("title"):
                        extracted_title = extracted["title"]
                    if extracted.get("author"):
                        author = extracted["author"]
                    if not images:
                        images = extract_images_from_html(cache_html, req.url)

        # ── Strategy 3: Wayback Machine ───────────────────────────────────
        if not content_text or len(content_text) < MIN_CONTENT_LENGTH:
            wb_html = await try_wayback_machine(client, req.url)
            if wb_html:
                extracted = best_extraction(wb_html, req.url)
                if len(extracted.get("text") or "") > len(content_text or ""):
                    content_text = extracted.get("text")
                    content_html = extracted.get("raw_html")
                    if extracted.get("title"):
                        extracted_title = extracted["title"]
                    if extracted.get("author"):
                        author = extracted["author"]
                    if not images:
                        images = extract_images_from_html(wb_html, req.url)

        # ── Fallback 1: RSS full content (content:encoded) ────────────────
        # Newsletter/Ghost/Substack sites publish the full article in content:encoded.
        # This beats web extraction on paywalled/JS-rendered pages.
        extraction_failed = False
        if not content_text or len(content_text) < MIN_CONTENT_LENGTH:
            rss_full = req.rss_content or ""
            if rss_full:
                extracted_from_rss = best_extraction(rss_full, req.url) if "<" in rss_full else {}
                rss_text = extracted_from_rss.get("text") or strip_html(rss_full)
                if len(rss_text) > len(content_text or ""):
                    content_text = rss_text
                    content_html = extracted_from_rss.get("raw_html") or text_to_html(rss_text)
                    if not extracted_title and extracted_from_rss.get("title"):
                        extracted_title = extracted_from_rss["title"]
                    if not author and extracted_from_rss.get("author"):
                        author = extracted_from_rss["author"]
                    if not images and "<img" in rss_full:
                        images = extract_images_from_html(rss_full, req.url)

        # ── Fallback 2: RSS summary ───────────────────────────────────────
        if not content_text or len(content_text) < 100:
            clean_summary = strip_html(req.rss_summary) if req.rss_summary else ""
            content_text = clean_summary or None
            content_html = text_to_html(clean_summary) if clean_summary else None
            extraction_failed = True

        final_title = resolve_title(extracted_title, req.rss_title, content_text)

        return ExtractResponse(
            title=final_title,
            content_html=content_html,
            content_text=content_text,
            images=images[:10],
            author=author,
            read_time_minutes=estimate_read_time(content_text or ""),
            extraction_failed=extraction_failed,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
