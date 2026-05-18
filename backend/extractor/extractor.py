import asyncio
import json
import os
import re
import time
from typing import Any, Callable, List, Optional
from urllib.parse import quote_plus, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup, Tag
from fastapi import FastAPI
from pydantic import BaseModel
from readability import Document

app = FastAPI(title="Baṣīra Extractor")

# ---------------------------------------------------------------------------
# Semantic Scholar rate limiting (module-level, shared across all requests)
# ---------------------------------------------------------------------------

_SS_LOCK = asyncio.Lock()
_ss_last_call: float = 0.0
SS_RATE_LIMIT_SECONDS = float(os.getenv("SS_RATE_LIMIT_SECONDS", "1.0"))

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

ARXIV_ABS_RE = re.compile(
    r"arxiv\.org/abs/(?P<id>[0-9]{4}\.[0-9]+(v\d+)?|[a-z\-]+/\d{7})", re.I
)
SUBSTACK_HOST_RE = re.compile(r"(^|\.)substack\.com$", re.I)


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

        paper_id_str = arxiv_paper_id(url) or ""
        base_pid = re.sub(r"v\d+$", "", paper_id_str) if paper_id_str else ""

        return {
            "title": title or None,
            "text": abstract,
            "author": authors or None,
            "raw_html": content_html,
            "is_paper": True,
            "source": "arxiv",
            "paper_id": base_pid or None,
            "doi": f"10.48550/arXiv.{base_pid}" if base_pid else None,
            "abstract": abstract,
            "authors": [a.strip() for a in (authors or "").split(",") if a.strip()],
            "year": None,
            "methods": [],
            "datasets": [],
            "metrics": [],
            "fields_of_study": subjects.split() if subjects else [],
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# SS rate-limited GET
# ---------------------------------------------------------------------------


async def _ss_rate_limited_get(
    client: httpx.AsyncClient, url: str, params=None
) -> Optional[httpx.Response]:
    """Serialise Semantic Scholar API calls and enforce SS_RATE_LIMIT_SECONDS."""
    global _ss_last_call
    async with _SS_LOCK:
        elapsed = time.monotonic() - _ss_last_call
        if elapsed < SS_RATE_LIMIT_SECONDS:
            await asyncio.sleep(SS_RATE_LIMIT_SECONDS - elapsed)
        try:
            resp = await client.get(url, params=params, timeout=10)
            return resp
        except Exception:
            return None
        finally:
            _ss_last_call = time.monotonic()


# ---------------------------------------------------------------------------
# Paper handlers — each returns a dict with keys: text, raw_html, title,
# author, is_paper, source, paper_id, doi, abstract, authors, year,
# methods, datasets, metrics, fields_of_study
# On failure they return {} or a minimal fallback dict.
# ---------------------------------------------------------------------------

_SS_FIELDS = "title,abstract,authors,year,externalIds,tldr,fieldsOfStudy"
_SS_BASE = "https://api.semanticscholar.org/graph/v1/paper"


def _build_paper_content_html(abstract: str, source: str, paper_id: str) -> str:
    """Build a minimal reader-facing HTML snippet for a paper."""
    return (
        f'<div class="paper-abstract"><p>{abstract}</p>'
        f'<p class="paper-source"><em>Source: {source} — {paper_id}</em></p></div>'
    )


async def _enrich_from_ss(
    client: httpx.AsyncClient, ss_query_id: str
) -> dict:
    """
    Query SS Graph API for a paper identified by `ss_query_id`
    (e.g. "arXiv:2401.12345", "ACL:2024.acl-long.1", or a 40-char S2 ID).
    Returns a partial paper_meta dict on success, {} on failure.
    """
    resp = await _ss_rate_limited_get(
        client, f"{_SS_BASE}/{ss_query_id}", params={"fields": _SS_FIELDS}
    )
    if not resp or resp.status_code != 200:
        return {}
    try:
        data = resp.json()
        abstract = data.get("abstract") or ""
        authors = [a.get("name", "") for a in (data.get("authors") or [])]
        year = data.get("year")
        ext_ids = data.get("externalIds") or {}
        doi = ext_ids.get("DOI")
        fields = [
            f.get("category", {}).get("name", "")
            for f in (data.get("fieldsOfStudy") or [])
        ]
        return {
            "abstract": abstract,
            "authors": authors,
            "year": year,
            "doi": doi,
            "fields_of_study": [f for f in fields if f],
        }
    except Exception:
        return {}


async def _extract_arxiv_handler(
    html: Optional[str], url: str, client: httpx.AsyncClient
) -> dict:
    """
    arXiv handler: HTML parse (existing logic) + optional SS enrichment.
    Refactored from the original extract_arxiv() — all HTML logic preserved.
    """
    base_result: dict = {}
    if html:
        base_result = extract_arxiv(html, url)

    paper_id_str = arxiv_paper_id(url) or ""
    base_pid = re.sub(r"v\d+$", "", paper_id_str) if paper_id_str else ""

    # Merge SS enrichment if available
    ss_data = {}
    if base_pid:
        ss_data = await _enrich_from_ss(client, f"arXiv:{base_pid}")

    abstract = ss_data.get("abstract") or base_result.get("abstract") or base_result.get("text", "")
    authors_list = ss_data.get("authors") or base_result.get("authors") or []
    year = ss_data.get("year")
    doi = ss_data.get("doi") or (f"10.48550/arXiv.{base_pid}" if base_pid else None)
    fields = ss_data.get("fields_of_study") or base_result.get("fields_of_study") or []

    if not base_result.get("text"):
        return {
            "is_paper": True,
            "source": "arxiv",
            "paper_id": base_pid or None,
        }

    return {
        "text": base_result["text"],
        "raw_html": base_result.get("raw_html"),
        "title": base_result.get("title"),
        "author": base_result.get("author"),
        "is_paper": True,
        "source": "arxiv",
        "paper_id": base_pid or None,
        "doi": doi,
        "abstract": abstract,
        "authors": authors_list,
        "year": year,
        "methods": [],
        "datasets": [],
        "metrics": [],
        "fields_of_study": fields,
    }


_SS_PAPER_ID_RE = re.compile(r"semanticscholar\.org/paper/[^/]+/([a-f0-9]{40})", re.I)


async def _extract_semantic_scholar_handler(
    html: Optional[str], url: str, client: httpx.AsyncClient
) -> dict:
    """Semantic Scholar page handler — queries the SS Graph API by S2 paper ID."""
    m = _SS_PAPER_ID_RE.search(url)
    if not m:
        return {"is_paper": True, "source": "semanticscholar"}

    s2_id = m.group(1)
    ss_data = await _enrich_from_ss(client, s2_id)
    if not ss_data or not ss_data.get("abstract"):
        fallback = {}
        if html:
            fallback = extract_with_readability(html, url) or extract_with_trafilatura(html, url)
        return {
            "is_paper": True,
            "source": "semanticscholar",
            "paper_id": s2_id,
            **({"text": fallback.get("text"), "raw_html": fallback.get("raw_html")} if fallback.get("text") else {}),
        }

    abstract = ss_data["abstract"]
    content_html = _build_paper_content_html(abstract, "Semantic Scholar", s2_id)
    return {
        "text": abstract,
        "raw_html": content_html,
        "title": None,
        "author": ", ".join(ss_data.get("authors") or []) or None,
        "is_paper": True,
        "source": "semanticscholar",
        "paper_id": s2_id,
        "doi": ss_data.get("doi"),
        "abstract": abstract,
        "authors": ss_data.get("authors") or [],
        "year": ss_data.get("year"),
        "methods": [],
        "datasets": [],
        "metrics": [],
        "fields_of_study": ss_data.get("fields_of_study") or [],
    }


_ACL_ID_RE = re.compile(r"aclanthology\.org/([A-Za-z0-9.\-]+?)(?:\.pdf)?/?$", re.I)


async def _extract_acl_anthology_handler(
    html: Optional[str], url: str, client: httpx.AsyncClient
) -> dict:
    """ACL Anthology handler — uses SS Graph API with ACL:{id} query."""
    m = _ACL_ID_RE.search(url)
    acl_id = m.group(1) if m else None

    ss_data = {}
    if acl_id:
        ss_data = await _enrich_from_ss(client, f"ACL:{acl_id}")

    abstract = ss_data.get("abstract", "")
    if not abstract and html:
        fallback = extract_with_readability(html, url) or extract_with_trafilatura(html, url)
        return {
            "is_paper": True,
            "source": "acl",
            "paper_id": acl_id,
            **({"text": fallback.get("text"), "raw_html": fallback.get("raw_html")} if fallback.get("text") else {}),
        }

    content_html = _build_paper_content_html(abstract, "ACL Anthology", acl_id or "")
    return {
        "text": abstract,
        "raw_html": content_html,
        "title": None,
        "author": ", ".join(ss_data.get("authors") or []) or None,
        "is_paper": True,
        "source": "acl",
        "paper_id": acl_id,
        "doi": ss_data.get("doi"),
        "abstract": abstract,
        "authors": ss_data.get("authors") or [],
        "year": ss_data.get("year"),
        "methods": [],
        "datasets": [],
        "metrics": [],
        "fields_of_study": ss_data.get("fields_of_study") or [],
    }


_OPENREVIEW_FORUM_RE = re.compile(r"openreview\.net/forum\?id=([A-Za-z0-9_\-]+)", re.I)


async def _extract_openreview_handler(
    html: Optional[str], url: str, client: httpx.AsyncClient
) -> dict:
    """OpenReview handler — queries the OpenReview API v2."""
    m = _OPENREVIEW_FORUM_RE.search(url)
    if not m:
        return {"is_paper": True, "source": "openreview"}

    forum_id = m.group(1)
    try:
        resp = await client.get(
            "https://api2.openreview.net/notes",
            params={"forum": forum_id, "select": "id,content"},
            timeout=10,
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenReview API returned {resp.status_code}")

        notes = resp.json().get("notes") or []
        if not notes:
            raise ValueError("No notes found")

        content = notes[0].get("content") or {}
        title_val = content.get("title", {})
        abstract_val = content.get("abstract", {})
        authors_val = content.get("authors", {})

        title = title_val.get("value") if isinstance(title_val, dict) else str(title_val)
        abstract = abstract_val.get("value") if isinstance(abstract_val, dict) else str(abstract_val)
        authors = authors_val.get("value") if isinstance(authors_val, dict) else []
        if isinstance(authors, str):
            authors = [authors]

    except Exception:
        if html:
            fallback = extract_with_readability(html, url) or extract_with_trafilatura(html, url)
            if fallback.get("text"):
                return {
                    "is_paper": True,
                    "source": "openreview",
                    "paper_id": forum_id,
                    "text": fallback["text"],
                    "raw_html": fallback.get("raw_html"),
                }
        return {"is_paper": True, "source": "openreview", "paper_id": forum_id}

    if not abstract:
        return {"is_paper": True, "source": "openreview", "paper_id": forum_id}

    content_html = _build_paper_content_html(abstract, "OpenReview", forum_id)
    return {
        "text": abstract,
        "raw_html": content_html,
        "title": title or None,
        "author": ", ".join(authors) if authors else None,
        "is_paper": True,
        "source": "openreview",
        "paper_id": forum_id,
        "doi": None,
        "abstract": abstract,
        "authors": authors,
        "year": None,
        "methods": [],
        "datasets": [],
        "metrics": [],
        "fields_of_study": [],
    }


def _extract_doi_from_url(url: str) -> Optional[str]:
    """Extract the raw DOI string from a doi.org URL."""
    parsed = urlparse(url)
    if "doi.org" in parsed.netloc.lower():
        doi = parsed.path.lstrip("/")
        return doi if doi else None
    return None


_JATS_TAG_RE = re.compile(r"<[^>]+>")


def _strip_jats(text: str) -> str:
    """Strip JATS XML tags that Crossref sometimes includes in abstracts."""
    return _JATS_TAG_RE.sub("", text).strip()


async def _extract_doi_handler(
    html: Optional[str], url: str, client: httpx.AsyncClient
) -> dict:
    """DOI handler — queries the Crossref API."""
    doi = _extract_doi_from_url(url)
    if not doi:
        return {"is_paper": True, "source": "doi"}

    try:
        resp = await client.get(
            f"https://api.crossref.org/works/{doi}",
            timeout=10,
            headers={"User-Agent": "Basira/1.0 (mailto:contact@example.com)"},
        )
        if resp.status_code != 200:
            raise ValueError(f"Crossref returned {resp.status_code}")

        msg = resp.json().get("message") or {}
        titles = msg.get("title") or []
        title = titles[0] if titles else None
        abstract_raw = msg.get("abstract") or ""
        abstract = _strip_jats(abstract_raw)
        raw_authors = msg.get("author") or []
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in raw_authors
        ]
        date_parts = (msg.get("published") or {}).get("date-parts") or [[]]
        year = date_parts[0][0] if date_parts[0] else None

    except Exception:
        if html:
            fallback = extract_with_readability(html, url) or extract_with_trafilatura(html, url)
            if fallback.get("text"):
                return {
                    "is_paper": True,
                    "source": "doi",
                    "paper_id": doi,
                    "doi": doi,
                    "text": fallback["text"],
                    "raw_html": fallback.get("raw_html"),
                }
        return {"is_paper": True, "source": "doi", "paper_id": doi, "doi": doi}

    if not abstract and not title:
        return {"is_paper": True, "source": "doi", "paper_id": doi, "doi": doi}

    text_content = abstract or title or ""
    content_html = _build_paper_content_html(text_content, "DOI/Crossref", doi)
    return {
        "text": text_content,
        "raw_html": content_html,
        "title": title or None,
        "author": ", ".join(authors) if authors else None,
        "is_paper": True,
        "source": "doi",
        "paper_id": doi,
        "doi": doi,
        "abstract": abstract,
        "authors": authors,
        "year": year,
        "methods": [],
        "datasets": [],
        "metrics": [],
        "fields_of_study": [],
    }


# ---------------------------------------------------------------------------
# Paper handler dispatcher
# ---------------------------------------------------------------------------

paper_handlers: List = [
    (lambda url: bool(ARXIV_ABS_RE.search(url)), _extract_arxiv_handler),
    (lambda url: "semanticscholar.org/paper/" in url.lower(), _extract_semantic_scholar_handler),
    (lambda url: "openreview.net/forum" in url.lower(), _extract_openreview_handler),
    (lambda url: "aclanthology.org/" in url.lower(), _extract_acl_anthology_handler),
    (
        lambda url: url.lower().startswith(("https://doi.org/", "http://doi.org/")),
        _extract_doi_handler,
    ),
]


def _detect_paper_handler(url: str) -> Optional[Callable]:
    """Return the first matching paper handler for this URL, or None."""
    for detect_fn, handler_fn in paper_handlers:
        if detect_fn(url):
            return handler_fn
    return None


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
    paper_meta: Optional[Any] = None     # structured paper metadata dict (Story 2.2)


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
        paper_meta_result: Optional[dict] = None

        # ── Strategy 0: Paper-source detection ────────────────────────────
        # Check paper_handlers dispatcher FIRST; structured API handlers
        # return richer metadata than generic readability extraction.
        detected_handler = _detect_paper_handler(req.url)
        if detected_handler is not None:
            # Fetch HTML (handler may or may not use it for fallback)
            html = await fetch_url(client, req.url)
            handler_result = await detected_handler(html, req.url, client)

            if handler_result.get("text"):
                content_text = handler_result["text"]
                content_html = handler_result.get("raw_html")
                extracted_title = handler_result.get("title")
                author = handler_result.get("author")
                # Build paper_meta from handler keys (exclude presentation keys)
                _skip = {"text", "raw_html", "title", "author"}
                paper_meta_result = {
                    k: v for k, v in handler_result.items() if k not in _skip
                }
                # Set canonical URL for arXiv
                if handler_result.get("source") == "arxiv" and handler_result.get("paper_id"):
                    canonical_url = f"https://arxiv.org/abs/{handler_result['paper_id']}"

                final_title = resolve_title(extracted_title, req.rss_title, content_text)
                return ExtractResponse(
                    title=final_title,
                    content_html=content_html,
                    content_text=content_text,
                    images=[],
                    author=author,
                    read_time_minutes=estimate_read_time(content_text or ""),
                    extraction_failed=False,
                    canonical_url=canonical_url,
                    paper_meta=paper_meta_result,
                )

            # Handler found but returned no text content — keep is_paper signal
            if handler_result.get("is_paper"):
                paper_meta_result = {
                    "is_paper": True,
                    "source": handler_result.get("source", "fallback"),
                    "paper_id": handler_result.get("paper_id"),
                }

            # Fallback: use RSS summary for arXiv (RSS includes the abstract)
            if arxiv_paper_id(req.url) and req.rss_summary:
                abstract = strip_html(req.rss_summary)
                pid = arxiv_paper_id(req.url)
                if pid:
                    base_pid = re.sub(r"v\d+$", "", pid)
                    canonical_url = f"https://arxiv.org/abs/{base_pid}"
                final_title = resolve_title(None, req.rss_title, abstract)
                return ExtractResponse(
                    title=final_title,
                    content_html=f"<p>{abstract}</p>",
                    content_text=abstract,
                    images=[],
                    author=None,
                    read_time_minutes=estimate_read_time(abstract),
                    extraction_failed=False,
                    canonical_url=canonical_url,
                    paper_meta=paper_meta_result,
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

        return ExtractResponse(
            title=final_title,
            content_html=content_html,
            content_text=content_text,
            images=images[:10],
            author=author,
            read_time_minutes=estimate_read_time(content_text or ""),
            extraction_failed=extraction_failed,
            canonical_url=canonical_url,
            paper_meta=paper_meta_result,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
