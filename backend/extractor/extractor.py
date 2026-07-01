import asyncio
import html as html_lib
import json
import re
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urlparse, urlunparse

import httpx
import bleach
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

ALLOWED_HTML_TAGS = frozenset(
    {
        "a",
        "abbr",
        "article",
        "aside",
        "b",
        "blockquote",
        "br",
        "caption",
        "cite",
        "code",
        "dd",
        "del",
        "details",
        "dfn",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "ins",
        "kbd",
        "li",
        "main",
        "mark",
        "ol",
        "p",
        "pre",
        "q",
        "s",
        "samp",
        "section",
        "small",
        "span",
        "strong",
        "sub",
        "summary",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "time",
        "tr",
        "u",
        "ul",
        "var",
    }
)
ALLOWED_HTML_PROTOCOLS = frozenset({"http", "https", "mailto"})
SAFE_LINK_TARGETS = frozenset({"_blank", "_self", "_parent", "_top"})
SAFE_LINK_REL = ("noopener", "noreferrer")
GLOBAL_HTML_ATTRS = frozenset({"class", "dir", "lang", "title"})
TAG_HTML_ATTRS = {
    "a": frozenset({"href", "rel", "target", "title"}),
    "blockquote": frozenset({"cite"}),
    "code": frozenset({"class"}),
    "img": frozenset({"alt", "height", "loading", "src", "title", "width"}),
    "pre": frozenset({"class"}),
    "q": frozenset({"cite"}),
    "td": frozenset({"colspan", "headers", "rowspan"}),
    "th": frozenset({"colspan", "headers", "rowspan", "scope"}),
    "time": frozenset({"datetime"}),
}

URL_ATTRS = frozenset({"cite", "href", "src"})

ARXIV_ABS_RE = re.compile(
    r"arxiv\.org/abs/(?P<id>[0-9]{4}\.[0-9]+(v\d+)?|[a-z\-]+/\d{7})", re.I
)
SUBSTACK_HOST_RE = re.compile(r"(^|\.)substack\.com$", re.I)
REDDIT_HOST_RE = re.compile(r"(^|\.)reddit\.com$", re.I)


def arxiv_paper_id(url: str) -> Optional[str]:
    m = ARXIV_ABS_RE.search(url)
    return m.group("id") if m else None


def extract_arxiv(html: str, url: str) -> dict:
    """
    Structured extraction for arxiv.org abstract pages.
    Returns title, abstract (as text+html), authors, categories.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Title — strip the "Title:" descriptor span
        title_tag = soup.find("h1", class_="title")
        title = ""
        if title_tag:
            for span in title_tag.find_all("span", class_="descriptor"):
                span.decompose()
            title = title_tag.get_text(separator=" ", strip=True)

        # Authors — strip the "Authors:" descriptor
        authors_tag = soup.find("div", class_="authors")
        authors = ""
        if authors_tag:
            for span in authors_tag.find_all("span", class_="descriptor"):
                span.decompose()
            authors = authors_tag.get_text(separator=", ", strip=True).strip(", ")

        # Abstract — strip the "Abstract:" descriptor
        abstract_tag = soup.find("blockquote", class_="abstract")
        abstract = ""
        if abstract_tag:
            for span in abstract_tag.find_all("span", class_="descriptor"):
                span.decompose()
            abstract = abstract_tag.get_text(separator=" ", strip=True)

        # Subjects/categories
        subjects_tag = soup.find("td", class_="tablecell subjects") or soup.find(
            "div", class_="subjects"
        )
        subjects = ""
        if subjects_tag:
            for span in subjects_tag.find_all("span", class_="descriptor"):
                span.decompose()
            subjects = subjects_tag.get_text(separator=" ", strip=True)

        if not abstract:
            return {}

        # Build clean content HTML
        paper_id = arxiv_paper_id(url) or ""
        pdf_url = f"https://arxiv.org/pdf/{paper_id}" if paper_id else ""
        html5_url = f"https://ar5iv.org/abs/{paper_id}" if paper_id else ""

        content_html = f"""<div class="arxiv-paper">
<p class="arxiv-abstract">{abstract}</p>
{f'<p class="arxiv-subjects"><em>{subjects}</em></p>' if subjects else ""}
<div class="arxiv-links">
{f'<a href="{pdf_url}" target="_blank" rel="noopener noreferrer" class="arxiv-pdf-link">📄 Open PDF</a>' if pdf_url else ""}
{f'<a href="{html5_url}" target="_blank" rel="noopener noreferrer" class="arxiv-html-link">🌐 HTML version (ar5iv)</a>' if html5_url else ""}
</div>
</div>"""

        return {
            "title": title or None,
            "text": abstract,
            "author": authors or None,
            "raw_html": content_html,
            "is_paper": True,
        }
    except Exception:
        return {}


class ExtractRequest(BaseModel):
    url: str
    rss_title: str = ""
    rss_summary: str = ""
    rss_content: str = (
        ""  # full content:encoded HTML from the feed (often complete article)
    )


class ExtractResponse(BaseModel):
    title: str
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images: List[str] = []
    author: Optional[str] = None
    read_time_minutes: int = 1
    extraction_failed: bool = False
    canonical_url: Optional[str] = None  # from <link rel="canonical"> in the page HTML


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
        1
        for c in sample
        if c == "\ufffd"  # UTF-8 replacement char
        or (ord(c) < 32 and c not in "\t\n\r")  # control chars except whitespace
    )
    return (bad / len(sample)) > 0.04  # >4% bad chars → garbled


# ---------------------------------------------------------------------------
# Canonical URL extraction
# ---------------------------------------------------------------------------


def extract_canonical_url(html: str, base_url: str) -> Optional[str]:
    """Return the <link rel="canonical"> href if present and absolute."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("link", rel="canonical")
        if not tag:
            return None
        href = (tag.get("href") or "").strip()
        if not href:
            return None
        if href.startswith("http://") or href.startswith("https://"):
            return href
        # Resolve relative canonical (e.g. /blog/post)
        parsed = urlparse(base_url)
        if href.startswith("/"):
            return f"{parsed.scheme}://{parsed.netloc}{href}"
    except Exception:
        pass
    return None


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
    return "\n".join(f"<p>{html_lib.escape(p)}</p>" for p in paragraphs)


def html_to_text(html: str) -> str:
    try:
        return BeautifulSoup(html, "html.parser").get_text(separator="\n\n", strip=True)
    except Exception:
        return ""


def is_safe_url_attr(attr: str, value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False

    parsed = urlparse(value)
    if not parsed.scheme:
        return True
    if attr == "src":
        return parsed.scheme.lower() in {"http", "https"}
    return parsed.scheme.lower() in ALLOWED_HTML_PROTOCOLS


def allow_article_attr(tag: str, attr: str, value: str) -> bool:
    attr = attr.lower()
    if attr.startswith("on") or attr == "style":
        return False
    if attr == "target" and value not in SAFE_LINK_TARGETS:
        return False
    if attr in URL_ATTRS and not is_safe_url_attr(attr, value):
        return False
    return attr in GLOBAL_HTML_ATTRS or attr in TAG_HTML_ATTRS.get(tag, frozenset())


def sanitize_article_html(raw: str, base_url: str) -> str:
    """Strip active/executable HTML while preserving normal article markup."""
    try:
        cleaner = bleach.Cleaner(
            tags=ALLOWED_HTML_TAGS,
            attributes=allow_article_attr,
            protocols=ALLOWED_HTML_PROTOCOLS,
            strip=True,
            strip_comments=True,
        )
        cleaned = cleaner.clean(raw or "")
        soup = BeautifulSoup(cleaned, "html.parser")

        for link in soup.find_all("a"):
            if not link.get("href"):
                continue
            raw_rel = link.get("rel") or []
            rel = set(raw_rel.split()) if isinstance(raw_rel, str) else set(raw_rel)
            rel.update(SAFE_LINK_REL)
            link["rel"] = " ".join(sorted(rel))

        for img in soup.find_all("img"):
            if not img.get("src"):
                img.decompose()

        return str(soup)
    except Exception:
        return bleach.clean(raw or "", tags=[], strip=True, strip_comments=True)


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
            return sanitize_article_html(outer.decode_contents(), base_url)

        return sanitize_article_html(str(soup), base_url)
    except Exception:
        return sanitize_article_html(raw, base_url)


def extract_images_from_html(
    html: str, base_url: str, max_images: int = 10
) -> List[str]:
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


def is_substack_url(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").split(":")[0].lower()
        return bool(SUBSTACK_HOST_RE.search(host))
    except Exception:
        return False


def is_reddit_url(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").split(":")[0].lower()
        return bool(REDDIT_HOST_RE.search(host))
    except Exception:
        return False


def reddit_json_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        if "/comments/" not in parsed.path:
            return None
        path = parsed.path.rstrip("/")
        if not path.endswith(".json"):
            path = f"{path}.json"
        return urlunparse(("https", "www.reddit.com", path, "", "raw_json=1", ""))
    except Exception:
        return None


def extract_reddit_rss_context(req: ExtractRequest) -> dict:
    """Build useful scoring context from Reddit RSS HTML when JSON is unavailable."""
    source_html = req.rss_content or req.rss_summary or ""
    source_text = strip_html(source_html)
    if not source_text and not req.rss_title:
        return {}

    external_links: list[str] = []
    try:
        soup = BeautifulSoup(source_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href.startswith(("http://", "https://")):
                continue
            host = (urlparse(href).netloc or "").lower()
            if "reddit.com" in host or href in external_links:
                continue
            external_links.append(href)
            if len(external_links) >= 3:
                break
    except Exception:
        pass

    lines = [
        "Reddit RSS item.",
        f"Title: {req.rss_title.strip()}" if req.rss_title.strip() else "",
        f"Post URL: {req.url}",
    ]
    if external_links:
        lines.append("External link(s): " + ", ".join(external_links))
    if source_text:
        lines.append(f"RSS context: {source_text[:1800]}")

    text = "\n".join(line for line in lines if line)
    if len(text) < 80:
        return {}

    return {
        "title": req.rss_title or None,
        "text": text,
        "author": None,
        "raw_html": text_to_html(text),
    }


async def extract_reddit_from_json(client: httpx.AsyncClient, req: ExtractRequest) -> dict:
    """Extract post metadata/body from Reddit's public JSON endpoint."""
    json_url = reddit_json_url(req.url)
    if not json_url:
        return {}

    try:
        resp = await client.get(
            json_url,
            headers={**HEADERS, "Accept": "application/json"},
            follow_redirects=True,
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        post = data[0]["data"]["children"][0]["data"]
    except Exception:
        return {}

    title = post.get("title") or req.rss_title
    selftext = post.get("selftext") or ""
    subreddit = post.get("subreddit") or ""
    author = post.get("author") or None
    score = post.get("score")
    comments = post.get("num_comments")
    flair = post.get("link_flair_text") or ""
    outbound_url = post.get("url_overridden_by_dest") or post.get("url") or ""
    permalink = post.get("permalink") or ""
    if permalink.startswith("/"):
        permalink = f"https://www.reddit.com{permalink}"

    is_external = outbound_url and is_reddit_url(req.url) and not is_reddit_url(outbound_url)
    lines = [
        f"Reddit post from r/{subreddit}." if subreddit else "Reddit post.",
        f"Title: {title}" if title else "",
        f"Author: u/{author}" if author else "",
        f"Score: {score}" if score is not None else "",
        f"Comments: {comments}" if comments is not None else "",
        f"Flair: {flair}" if flair else "",
        f"Post URL: {permalink or req.url}",
        f"External link: {outbound_url}" if is_external else "",
    ]
    if selftext:
        lines.append(f"Post body:\n{selftext[:3000]}")

    top_comments: list[str] = []
    try:
        for child in data[1]["data"]["children"]:
            cdata = child.get("data", {})
            body = (cdata.get("body") or "").strip()
            if not body:
                continue
            cscore = cdata.get("score")
            top_comments.append(f"- score {cscore}: {body[:500]}")
            if len(top_comments) >= 3:
                break
    except Exception:
        pass
    if top_comments:
        lines.append("Top comment excerpts:\n" + "\n".join(top_comments))

    text = "\n".join(line for line in lines if line)
    if len(text) < 80:
        return {}

    content_html = "\n".join(
        f"<p>{html_lib.escape(line).replace(chr(10), '<br>')}</p>"
        for line in lines
        if line
    )
    return {
        "title": title or None,
        "text": text,
        "author": author,
        "raw_html": content_html,
    }


def extract_substack_body_html(html: str) -> Optional[str]:
    """
    Substack pages often embed full article HTML in JS payload as "body_html".
    Decode that payload directly to avoid weak extraction/fallbacks.
    """
    patterns = [
        r'"body_html"\s*:\s*"((?:\\.|[^"\\])*)"',
        r'"bodyHtml"\s*:\s*"((?:\\.|[^"\\])*)"',
    ]
    best = None

    for pattern in patterns:
        for match in re.finditer(pattern, html):
            try:
                candidate = json.loads(f'"{match.group(1)}"')
            except Exception:
                continue
            if not candidate or "<" not in candidate:
                continue
            if best is None or len(candidate) > len(best):
                best = candidate

    return best


def extract_substack_from_html(html: str, url: str) -> dict:
    """Substack-specific extraction from embedded payload and metadata."""
    if not is_substack_url(url):
        return {}

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Metadata fallbacks
        title = clean_title(
            (soup.find("meta", property="og:title") or {}).get("content")
            or (soup.find("meta", attrs={"name": "twitter:title"}) or {}).get("content")
            or (soup.title.get_text(strip=True) if soup.title else None)
        )

        author = (
            (soup.find("meta", attrs={"name": "author"}) or {}).get("content")
            or (soup.find("meta", property="article:author") or {}).get("content")
            or (soup.find("meta", attrs={"name": "dc.creator"}) or {}).get("content")
        )

        body_html = extract_substack_body_html(html)
        if not body_html:
            return {}

        content_html = clean_readability_html(body_html, url)
        content_text = html_to_text(content_html)
        if len(content_text) < MIN_CONTENT_LENGTH:
            return {}

        return {
            "title": title,
            "text": content_text,
            "author": author,
            "raw_html": content_html,
        }
    except Exception:
        return {}


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
        raw_html = clean_readability_html(raw_html, url)

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
    cache_url = (
        f"https://webcache.googleusercontent.com/search?q=cache:{quote_plus(url)}"
    )
    return await fetch_url(client, cache_url)


async def try_wayback_machine(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        resp = await client.get(
            f"https://archive.org/wayback/available?url={quote_plus(url)}", timeout=10
        )
        if resp.status_code == 200:
            snapshot_url = (
                resp.json().get("archived_snapshots", {}).get("closest", {}).get("url")
            )
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
            return first + (
                "…" if len(content_text.strip().split("\n")[0]) > 120 else ""
            )

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
        canonical_url: Optional[str] = None

        # ── Strategy 0: ArXiv special extraction ─────────────────────────
        # arxiv.org/abs/ pages have structured HTML — extract abstract,
        # title, authors, categories directly instead of using readability.
        if arxiv_paper_id(req.url):
            html = await fetch_url(client, req.url)
            if html:
                arxiv_data = extract_arxiv(html, req.url)
                if arxiv_data.get("text"):
                    content_text = arxiv_data["text"]
                    content_html = sanitize_article_html(arxiv_data["raw_html"], req.url)
                    extracted_title = arxiv_data.get("title")
                    author = arxiv_data.get("author")
                    # Canonical: strip version suffix  (abs/2501.12345v2 → abs/2501.12345)
                    pid = arxiv_paper_id(req.url)
                    if pid:
                        base_pid = re.sub(r"v\d+$", "", pid)
                        canonical_url = f"https://arxiv.org/abs/{base_pid}"
                    # Return early — no need for other strategies
                    final_title = resolve_title(
                        extracted_title, req.rss_title, content_text
                    )
                    return ExtractResponse(
                        title=final_title,
                        content_html=content_html,
                        content_text=content_text,
                        images=[],
                        author=author,
                        read_time_minutes=estimate_read_time(content_text or ""),
                        extraction_failed=False,
                        canonical_url=canonical_url,
                    )
            # Fallback: use RSS summary (ArXiv RSS includes the abstract)
            if req.rss_summary:
                abstract = strip_html(req.rss_summary)
                final_title = resolve_title(None, req.rss_title, abstract)
                return ExtractResponse(
                    title=final_title,
                    content_html=sanitize_article_html(text_to_html(abstract), req.url),
                    content_text=abstract,
                    images=[],
                    author=None,
                    read_time_minutes=estimate_read_time(abstract),
                    extraction_failed=False,
                    canonical_url=canonical_url,
                )

        # ── Strategy 0b: Reddit post extraction ──────────────────────────
        # Reddit RSS entries usually point at comment pages. Fetch the public
        # JSON form first so the scorer receives post body, score/comment
        # counts, outbound link, and a few comment excerpts instead of only a
        # brittle scraped page title.
        if is_reddit_url(req.url):
            reddit_data = await extract_reddit_from_json(client, req)
            if not reddit_data:
                reddit_data = extract_reddit_rss_context(req)
            if reddit_data.get("text"):
                content_text = reddit_data["text"]
                content_html = sanitize_article_html(reddit_data["raw_html"], req.url)
                extracted_title = reddit_data.get("title")
                author = reddit_data.get("author")
                final_title = resolve_title(extracted_title, req.rss_title, content_text)
                return ExtractResponse(
                    title=final_title,
                    content_html=content_html,
                    content_text=content_text,
                    images=[],
                    author=author,
                    read_time_minutes=estimate_read_time(content_text or ""),
                    extraction_failed=len(content_text or "") < MIN_CONTENT_LENGTH,
                    canonical_url=None,
                )

        # ── Strategy 1: direct fetch ──────────────────────────────────────
        html = await fetch_url(client, req.url)
        if html:
            extracted = best_extraction(html, req.url)
            content_text = extracted.get("text")
            content_html = extracted.get("raw_html")
            extracted_title = extracted.get("title")
            author = extracted.get("author")
            images = extract_images_from_html(html, req.url)
            # Extract canonical URL — the site's own authoritative URL for this page.
            # If it differs from the requested URL, use it as the dedup key so the
            # same article reached via different paths is only stored once.
            raw_canonical = extract_canonical_url(html, req.url)
            if raw_canonical and raw_canonical.rstrip("/") != req.url.rstrip("/"):
                canonical_url = raw_canonical

            # Substack pages frequently include full article HTML in embedded JSON.
            # Prefer this source before remote archive fallbacks.
            if is_substack_url(req.url) and (
                not content_text or len(content_text) < MIN_CONTENT_LENGTH
            ):
                substack = extract_substack_from_html(html, req.url)
                if len(substack.get("text") or "") > len(content_text or ""):
                    content_text = substack.get("text")
                    content_html = substack.get("raw_html")
                    if substack.get("title"):
                        extracted_title = substack["title"]
                    if substack.get("author"):
                        author = substack["author"]
                    if not images:
                        images = extract_images_from_html(content_html or "", req.url)

        # ── Fallback 1: RSS full content (content:encoded) ────────────────
        # Newsletter/Ghost/Substack sites may expose full article HTML in feeds.
        if not content_text or len(content_text) < MIN_CONTENT_LENGTH:
            rss_full = req.rss_content or ""
            if rss_full:
                extracted_from_rss = (
                    best_extraction(rss_full, req.url) if "<" in rss_full else {}
                )
                rss_text = extracted_from_rss.get("text") or strip_html(rss_full)
                if len(rss_text) > len(content_text or ""):
                    content_text = rss_text
                    content_html = extracted_from_rss.get("raw_html") or text_to_html(
                        rss_text
                    )
                    if not extracted_title and extracted_from_rss.get("title"):
                        extracted_title = extracted_from_rss["title"]
                    if not author and extracted_from_rss.get("author"):
                        author = extracted_from_rss["author"]
                    if not images:
                        images = extract_images_from_html(rss_full, req.url)

        # ── Fallback 2: RSS summary (often rich HTML for newsletters) ─────
        if not content_text or len(content_text) < MIN_CONTENT_LENGTH:
            rss_summary = req.rss_summary or ""
            if rss_summary:
                summary_text = strip_html(rss_summary)
                if len(summary_text) >= 100:
                    content_text = summary_text
                    content_html = (
                        rss_summary
                        if "<" in rss_summary
                        else text_to_html(summary_text)
                    )
                    if not images:
                        images = extract_images_from_html(content_html or "", req.url)

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

        extraction_failed = False

        # ── Final fallback: short RSS summary ─────────────────────────────
        if not content_text or len(content_text) < 100:
            clean_summary = strip_html(req.rss_summary) if req.rss_summary else ""
            content_text = clean_summary or None
            content_html = text_to_html(clean_summary) if clean_summary else None
            extraction_failed = True

        final_title = resolve_title(extracted_title, req.rss_title, content_text)
        content_html = (
            sanitize_article_html(content_html, req.url) if content_html else None
        )

        return ExtractResponse(
            title=final_title,
            content_html=content_html,
            content_text=content_text,
            images=images[:10],
            author=author,
            read_time_minutes=estimate_read_time(content_text or ""),
            extraction_failed=extraction_failed,
            canonical_url=canonical_url,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
