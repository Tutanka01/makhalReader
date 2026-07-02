from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extractor import extract_images_from_html, extract_og_image

BASE = "https://developer-blogs.nvidia.com/blog/scaling-ai-inference/"


def test_skips_theme_logo_and_svg_site_chrome():
    html = """
    <header>
      <img src="https://developer-blogs.nvidia.com/wp-content/themes/nvidia/dist/images/nvidia-logo_28b633c7.svg" alt="logo">
    </header>
    <article>
      <img src="https://developer-blogs.nvidia.com/wp-content/uploads/2026/06/AI-Inference-1024x576.jpg" alt="hero">
    </article>
    """
    images = extract_images_from_html(html, BASE)
    assert images == [
        "https://developer-blogs.nvidia.com/wp-content/uploads/2026/06/AI-Inference-1024x576.jpg"
    ]


def test_skips_icons_avatars_and_tracking_pixels():
    html = """
    <img src="/assets/favicon.ico">
    <img src="/img/icons/rss-icon.png">
    <img src="https://secure.gravatar.com/avatar/abc123.png">
    <img src="/stats/pixel.gif" width="1" height="1">
    <img src="/uploads/silicon-photonics.jpg">
    """
    images = extract_images_from_html(html, BASE)
    assert images == ["https://developer-blogs.nvidia.com/uploads/silicon-photonics.jpg"]


def test_skips_tiny_images_by_dimensions():
    html = """
    <img src="/uploads/decorative.png" width="48" height="48">
    <img src="/uploads/diagram.png" width="1200" height="800">
    """
    images = extract_images_from_html(html, BASE)
    assert images == ["https://developer-blogs.nvidia.com/uploads/diagram.png"]


def test_uses_lazyload_data_src_and_dedupes():
    html = """
    <img class="lazyload" src="data:image/gif;base64,R0lGOD" data-src="/uploads/figure-1.webp">
    <img src="/uploads/figure-1.webp">
    <img data-src="/uploads/figure-2.webp">
    """
    images = extract_images_from_html(html, BASE)
    assert images == [
        "https://developer-blogs.nvidia.com/uploads/figure-1.webp",
        "https://developer-blogs.nvidia.com/uploads/figure-2.webp",
    ]


def test_extract_og_image_prefers_meta_tag():
    html = """
    <html><head>
      <meta property="og:image" content="/wp-content/uploads/2026/06/AI-Inference.jpg">
    </head><body></body></html>
    """
    assert (
        extract_og_image(html, BASE)
        == "https://developer-blogs.nvidia.com/wp-content/uploads/2026/06/AI-Inference.jpg"
    )


def test_extract_og_image_ignores_chrome_and_missing():
    assert extract_og_image("<html></html>", BASE) is None
    html = '<meta property="og:image" content="/themes/site/logo.svg">'
    assert extract_og_image(html, BASE) is None
