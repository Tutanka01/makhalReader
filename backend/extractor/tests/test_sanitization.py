from pathlib import Path
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extractor
from extractor import clean_readability_html, sanitize_article_html


def test_sanitize_removes_scripts_handlers_styles_and_unsafe_protocols():
    raw = """
    <article onclick="steal()">
      <h2>Useful heading</h2>
      <p style="color:red">Hello <strong>reader</strong></p>
      <script>alert(1)</script>
      <img src="javascript:alert(1)" onerror="alert(1)" alt="bad">
      <a href="javascript:alert(1)" target="_blank">bad link</a>
      <form><input name="email"></form>
      <iframe src="https://example.com/embed"></iframe>
    </article>
    """

    cleaned = sanitize_article_html(raw, "https://example.com/posts/one")

    assert "<script" not in cleaned
    assert "onclick" not in cleaned
    assert "onerror" not in cleaned
    assert "style=" not in cleaned
    assert "javascript:" not in cleaned
    assert "<form" not in cleaned
    assert "<iframe" not in cleaned
    assert "<h2>Useful heading</h2>" in cleaned
    assert "<strong>reader</strong>" in cleaned
    assert "<img" not in cleaned


def test_clean_readability_html_preserves_article_markup_and_secures_links():
    raw = """
    <div id="readability-page-1">
      <h1>Article title</h1>
      <p>Intro with <em>emphasis</em> and <code>code()</code>.</p>
      <blockquote cite="/source">quoted text</blockquote>
      <pre><code class="language-python">print("ok")</code></pre>
      <table><thead><tr><th scope="col">Name</th></tr></thead><tbody><tr><td>Value</td></tr></tbody></table>
      <a href="/posts/next" target="_blank" rel="nofollow">next</a>
      <img src="/images/pic.jpg" alt="A picture" width="640" height="320">
    </div>
    """

    cleaned = clean_readability_html(raw, "https://example.com/articles/current")

    assert "<h1>Article title</h1>" in cleaned
    assert "<blockquote cite=\"/source\">quoted text</blockquote>" in cleaned
    assert "<pre><code class=\"language-python\">" in cleaned
    assert "<table>" in cleaned
    assert "href=\"https://example.com/posts/next\"" in cleaned
    assert "target=\"_blank\"" in cleaned
    assert "noopener" in cleaned
    assert "noreferrer" in cleaned
    assert "rel=\"nofollow noopener noreferrer\"" in cleaned
    assert "src=\"https://example.com/images/pic.jpg\"" in cleaned


def test_sanitize_keeps_safe_mailto_and_removes_unsafe_data_image():
    raw = """
    <p>
      <a href="mailto:editor@example.com">email</a>
      <img src="data:image/svg+xml,<svg onload=alert(1)>" alt="inline">
    </p>
    """

    cleaned = sanitize_article_html(raw, "https://example.com")

    assert "href=\"mailto:editor@example.com\"" in cleaned
    assert "noopener" in cleaned
    assert "noreferrer" in cleaned
    assert "<img" not in cleaned
    assert "data:image" not in cleaned


def test_extract_sanitizes_rss_summary_fallback_before_response():
    async def fake_fetch(*args, **kwargs):
        return None

    old_fetch_url = extractor.fetch_url
    old_google_cache = extractor.try_google_cache
    old_wayback = extractor.try_wayback_machine
    extractor.fetch_url = fake_fetch
    extractor.try_google_cache = fake_fetch
    extractor.try_wayback_machine = fake_fetch
    try:
        summary = """
        <p onclick="alert(1)">Useful summary text that is deliberately long enough
        to pass the rich RSS fallback threshold and represent a newsletter body.
        This paragraph contains article content worth preserving for the reader.</p>
        <script>alert(1)</script>
        <a href="javascript:alert(1)" target="_blank">bad</a>
        <img src="/cover.jpg" alt="Cover" onerror="alert(1)">
        """
        response = asyncio.run(
            extractor.extract(
                extractor.ExtractRequest(
                    url="https://example.com/post",
                    rss_title="RSS title",
                    rss_summary=summary,
                )
            )
        )
    finally:
        extractor.fetch_url = old_fetch_url
        extractor.try_google_cache = old_google_cache
        extractor.try_wayback_machine = old_wayback

    assert response.content_html is not None
    assert "Useful summary text" in response.content_html
    assert "<script" not in response.content_html
    assert "onclick" not in response.content_html
    assert "onerror" not in response.content_html
    assert "javascript:" not in response.content_html
    assert "src=\"/cover.jpg\"" in response.content_html


if __name__ == "__main__":
    test_sanitize_removes_scripts_handlers_styles_and_unsafe_protocols()
    test_clean_readability_html_preserves_article_markup_and_secures_links()
    test_sanitize_keeps_safe_mailto_and_removes_unsafe_data_image()
    test_extract_sanitizes_rss_summary_fallback_before_response()
