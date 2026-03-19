import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import feedparser
import httpx
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

API_BASE = "http://api:8000"
EXTRACTOR_BASE = "http://extractor:8001"
SCORER_BASE = "http://scorer:8002"
API_SECRET = os.getenv("API_SECRET", "changeme")
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "15"))

# --- Guardrails ---
# Max new articles ingested per feed per poll cycle.
MAX_NEW_PER_FEED = int(os.getenv("MAX_NEW_ARTICLES_PER_FEED", "5"))
# Articles older than this are skipped entirely (not stored, not scored).
MAX_ARTICLE_AGE_DAYS = int(os.getenv("MAX_ARTICLE_AGE_DAYS", "7"))
# Minimum seconds between two consecutive LLM scoring calls (global, all feeds).
SCORE_DELAY_SECONDS = float(os.getenv("SCORE_DELAY_SECONDS", "2.0"))

INTERNAL_HEADERS = {"X-Internal-Secret": API_SECRET, "Content-Type": "application/json"}

# ---------------------------------------------------------------------------
# URL normalisation — canonical form used for deduplication
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_name", "utm_cid",
    "fbclid", "gclid", "msclkid", "yclid", "twclid", "igshid",
    "_ga", "_gl", "mc_cid", "mc_eid", "ref", "source",
})


def normalize_url(url: str) -> str:
    """Return a canonical URL: lowercase scheme+host, strip www., remove
    tracking query params, sort remaining params, strip trailing slash."""
    try:
        p = urlparse(url.strip())
        scheme = p.scheme.lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path.rstrip("/") or "/"
        params = parse_qs(p.query, keep_blank_values=False)
        clean = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
        query = urlencode(sorted(clean.items()), doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url

# Global semaphore: only one LLM call at a time across all concurrent feed processing.
_score_semaphore = asyncio.Semaphore(1)


# ---------------------------------------------------------------------------
# HTTP helpers (all retried)
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_feeds(client: httpx.AsyncClient) -> list:
    resp = await client.get(f"{API_BASE}/api/feeds", timeout=30)
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def check_article_exists(client: httpx.AsyncClient, url: str) -> bool:
    resp = await client.get(
        f"{API_BASE}/api/articles",
        params={"url": url, "status": "all", "limit": 1},
        timeout=10,
    )
    resp.raise_for_status()
    return len(resp.json()) > 0


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def extract_article(
    client: httpx.AsyncClient,
    url: str,
    rss_title: str,
    rss_summary: str,
    rss_content: str = "",
) -> dict:
    resp = await client.post(
        f"{EXTRACTOR_BASE}/extract",
        json={
            "url": url,
            "rss_title": rss_title,
            "rss_summary": rss_summary,
            "rss_content": rss_content,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def create_article(client: httpx.AsyncClient, payload: dict) -> dict:
    resp = await client.post(
        f"{API_BASE}/api/internal/articles",
        json=payload,
        headers=INTERNAL_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def score_article_rate_limited(
    client: httpx.AsyncClient,
    article_id: int,
    title: str,
    content_text: str,
    rss_summary: str,
):
    """Acquire the global semaphore before calling the scorer, then wait SCORE_DELAY_SECONDS."""
    async with _score_semaphore:
        try:
            resp = await client.post(
                f"{SCORER_BASE}/score",
                json={
                    "article_id": article_id,
                    "title": title,
                    "content_text": content_text or "",
                    "rss_summary": rss_summary or "",
                },
                timeout=120,
            )
            resp.raise_for_status()
        finally:
            # Always wait, even on error, to avoid hammering the LLM on retries.
            await asyncio.sleep(SCORE_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# Entry helpers
# ---------------------------------------------------------------------------

def parse_published_dt(entry) -> datetime | None:
    """Return a timezone-aware datetime or None."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def is_too_old(entry) -> bool:
    """Return True if the article is older than MAX_ARTICLE_AGE_DAYS."""
    dt = parse_published_dt(entry)
    if dt is None:
        # No date in the feed → keep it (can't know, and first-time feeds
        # often have undated entries; they will be skipped on next cycle
        # because they'll already exist in the DB).
        return False
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
    return dt < cutoff


# ---------------------------------------------------------------------------
# Core polling logic
# ---------------------------------------------------------------------------

async def process_feed(client: httpx.AsyncClient, feed: dict):
    feed_id = feed["id"]
    feed_url = feed["url"]
    feed_name = feed["name"]
    log = logger.bind(feed=feed_name)

    log.info("Polling feed")
    try:
        parsed = await asyncio.to_thread(feedparser.parse, feed_url)
    except Exception as e:
        log.error("Failed to parse feed", error=str(e))
        return

    all_entries = parsed.entries
    log.info(f"Feed has {len(all_entries)} entries in RSS")

    # 1. Drop entries that are too old before any DB check.
    fresh_entries = [e for e in all_entries if not is_too_old(e)]
    skipped_old = len(all_entries) - len(fresh_entries)
    if skipped_old:
        log.info(f"Skipped {skipped_old} entries older than {MAX_ARTICLE_AGE_DAYS} days")

    new_count = 0

    for entry in fresh_entries:
        if new_count >= MAX_NEW_PER_FEED:
            log.info(f"Reached MAX_NEW_ARTICLES_PER_FEED={MAX_NEW_PER_FEED}, stopping feed")
            break

        raw_url = getattr(entry, "link", None)
        if not raw_url:
            continue
        article_url = normalize_url(raw_url)

        try:
            # Check both the canonical (normalized) URL and the original URL so that
            # articles ingested before URL normalization was introduced are not
            # re-extracted and re-scored on every poll cycle.
            exists = await check_article_exists(client, article_url)
            if not exists and raw_url != article_url:
                exists = await check_article_exists(client, raw_url)
            if exists:
                continue
        except Exception as e:
            log.warning("Failed to check article existence", url=article_url, error=str(e))
            continue

        rss_title = getattr(entry, "title", "") or ""
        rss_summary = getattr(entry, "summary", "") or ""
        # content:encoded — full article HTML, present in many newsletter/Ghost feeds
        rss_content = ""
        if hasattr(entry, "content") and entry.content:
            rss_content = entry.content[0].get("value", "") or ""
        rss_author = getattr(entry, "author", "") or None
        published_dt = parse_published_dt(entry)
        published_at = published_dt.isoformat() if published_dt else None

        log.info("Extracting article", url=article_url)
        try:
            extracted = await extract_article(client, article_url, rss_title, rss_summary, rss_content)
        except Exception as e:
            log.error("Extraction failed", url=article_url, error=str(e))
            extracted = {
                "title": rss_title,
                "content_html": None,
                "content_text": rss_summary,
                "images": [],
                "author": rss_author,
                "extraction_failed": True,
            }

        payload = {
            "feed_id": feed_id,
            "title": extracted.get("title") or rss_title,
            "url": article_url,
            "published_at": published_at,
            "author": extracted.get("author") or rss_author,
            "content_html": extracted.get("content_html"),
            "content_text": extracted.get("content_text"),
            "images": extracted.get("images", []),
            "extraction_failed": extracted.get("extraction_failed", False),
        }

        try:
            result = await create_article(client, payload)
        except Exception as e:
            log.error("Failed to create article", url=article_url, error=str(e))
            continue

        if not result.get("created", False):
            continue

        article_id = result["id"]
        new_count += 1
        log.info("Article stored, sending to scorer", article_id=article_id, new_count=new_count)

        try:
            await score_article_rate_limited(
                client,
                article_id,
                extracted.get("title") or rss_title,
                extracted.get("content_text") or rss_summary,
                rss_summary,
            )
            log.info("Article scored", article_id=article_id)
        except Exception as e:
            log.error("Scoring failed", article_id=article_id, error=str(e))

    log.info(f"Feed done: {new_count} new articles ingested")


async def poll_all_feeds():
    logger.info(
        "Starting poll cycle",
        max_new_per_feed=MAX_NEW_PER_FEED,
        max_age_days=MAX_ARTICLE_AGE_DAYS,
        score_delay_s=SCORE_DELAY_SECONDS,
    )
    async with httpx.AsyncClient() as client:
        try:
            feeds = await fetch_feeds(client)
        except Exception as e:
            logger.error("Failed to fetch feeds", error=str(e))
            return

        # Process feeds concurrently — scoring is serialised by _score_semaphore.
        await asyncio.gather(*[process_feed(client, feed) for feed in feeds], return_exceptions=True)

    logger.info("Poll cycle complete")


# ---------------------------------------------------------------------------
# Startup + scheduler
# ---------------------------------------------------------------------------

async def wait_for_api():
    logger.info("Waiting for API to be ready...")
    await asyncio.sleep(10)
    for attempt in range(30):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/api/health", timeout=5)
                if resp.status_code == 200:
                    logger.info("API is ready")
                    return
        except Exception:
            pass
        logger.info(f"API not ready, retry {attempt + 1}/30...")
        await asyncio.sleep(5)
    logger.error("API never became ready, starting scheduler anyway")


async def main():
    await wait_for_api()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        poll_all_feeds,
        "interval",
        minutes=FETCH_INTERVAL_MINUTES,
        id="poll_feeds",
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info(f"Scheduler running, interval={FETCH_INTERVAL_MINUTES}min")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
