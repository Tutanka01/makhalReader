"""
Tests for all source providers — Stories 12.3 + 12.4.

Run:
    python backend/extractor/test_source_providers.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Pre-seed httpx before any provider import
sys.modules["httpx"] = MagicMock()

_extractor_dir = os.path.dirname(os.path.abspath(__file__))
for p in [_extractor_dir, os.path.join(_extractor_dir, "..", "api")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Mock net_guard before importing provider modules
import net_guard
net_guard.check_url = MagicMock()
net_guard.SSRFBlockedError = type("SSRFBlockedError", (Exception,), {})

# Providers that import check_url directly get a local reference
import providers.generic_rss as _grss_mod
_grss_mod.check_url = MagicMock()  # override local reference

from providers import PROVIDER_REGISTRY
from providers.arxiv import ArxivProvider, ARXIV_CATEGORY_MAP
from providers.base import FetchedArticle, ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  \u2705  {name}")


def _fail(name: str, msg: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  \u274c  {name}: {msg}")


def _assert_true(name: str, cond: bool) -> None:
    if cond:
        _ok(name)
    else:
        _fail(name, f"expected True, got {cond!r}")


def _assert_eq(name: str, actual: Any, expected: Any) -> None:
    if actual == expected:
        _ok(name)
    else:
        _fail(name, f"expected {expected!r}, got {actual!r}")


def _assert_in(name: str, needle: str, haystack: str) -> None:
    if needle in haystack:
        _ok(name)
    else:
        _fail(name, f"{needle!r} not found in {haystack!r}")


def _mock_async_client(
    get_responses: dict[str, Any],
    fail_on_extra: bool = True,
) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock()

    async def side_effect(url: str, **kwargs: Any) -> MagicMock:
        for key, data in get_responses.items():
            if key in url:
                resp = MagicMock()
                resp.status_code = 200
                resp.json = MagicMock(return_value=data)
                resp.text = data.get("_text", "")
                return resp
        if fail_on_extra:
            raise AssertionError(f"Unexpected URL: {url}")
        resp = MagicMock()
        resp.status_code = 404
        resp.json = MagicMock(return_value={})
        resp.text = ""
        return resp

    client.get.side_effect = side_effect
    return client


# ══════════════════════════════════════════════════════════════════════════════
# 1. Base model & registry tests
# ══════════════════════════════════════════════════════════════════════════════

def test_base_models() -> None:
    si = SourceIntent(query="machine learning", category="research")
    _assert_eq("SourceIntent query", si.query, "machine learning")
    _assert_eq("SourceIntent category", si.category, "research")

    rs = ResolvedSource(name="Test", provider="openalex", query_json={"key": "val"})
    _assert_eq("ResolvedSource name", rs.name, "Test")
    _assert_eq("ResolvedSource provider", rs.provider, "openalex")

    vs = VerifiedSource(verified=True, sample_count=10)
    _assert_eq("VerifiedSource verified", vs.verified, True)
    _assert_eq("VerifiedSource sample_count", vs.sample_count, 10)


def test_source_provider_abc() -> None:
    _assert_true("SourceProvider has provider_id", hasattr(SourceProvider, "provider_id"))
    _assert_true("SourceProvider has resolve", hasattr(SourceProvider, "resolve"))
    _assert_true("SourceProvider has verify", hasattr(SourceProvider, "verify"))


def test_provider_registry_contains_all() -> None:
    expected = {"openalex", "crossref", "arxiv", "doaj", "hal", "dblp", "openreview", "rss"}
    _assert_eq("PROVIDER_REGISTRY keys", set(PROVIDER_REGISTRY.keys()), expected)


# ══════════════════════════════════════════════════════════════════════════════
# 2. OpenAlexProvider tests
# ══════════════════════════════════════════════════════════════════════════════

OPENALEX_SOURCES_RESPONSE = {
    "results": [
        {"id": "https://openalex.org/S123", "display_name": "Journal of AI Research", "type": "journal"},
        {"id": "https://openalex.org/S456", "display_name": "Machine Learning Review", "type": "journal"},
    ],
}
OPENALEX_CONCEPTS_RESPONSE = {
    "results": [
        {"id": "https://openalex.org/C123", "display_name": "Machine Learning", "type": "concept"},
    ],
}
OPENALEX_WORKS_WITH_RESULTS = {"meta": {"count": 42}}
OPENALEX_WORKS_EMPTY = {"meta": {"count": 0}}


def test_openalex_provider_id() -> None:
    from providers.openalex import OpenAlexProvider
    _assert_eq("provider_id", OpenAlexProvider.provider_id, "openalex")


def test_openalex_resolve_returns_results() -> None:
    from providers.openalex import OpenAlexProvider
    client = _mock_async_client({"sources": OPENALEX_SOURCES_RESPONSE, "concepts": OPENALEX_CONCEPTS_RESPONSE})
    provider = OpenAlexProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="machine learning")))
    _assert_true("has results", len(results) > 0)
    for r in results:
        _assert_eq(f"provider={r.provider}", r.provider, "openalex")
        _assert_true(f"name={r.name}", bool(r.name))
        _assert_true(f"label={r.label}", bool(r.label))


def test_openalex_resolve_empty_query_returns_empty() -> None:
    from providers.openalex import OpenAlexProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = OpenAlexProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="")))
    _assert_eq("empty", results, [])


def test_openalex_verify_returns_verified_true() -> None:
    from providers.openalex import OpenAlexProvider
    client = _mock_async_client({"works": OPENALEX_WORKS_WITH_RESULTS})
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(name="Test", provider="openalex", query_json={"source_id": "S123"}, provenance_url="https://openalex.org/S123")
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)
    _assert_eq("count=42", result.sample_count, 42)


def test_openalex_verify_returns_false_when_empty() -> None:
    from providers.openalex import OpenAlexProvider
    client = _mock_async_client({"works": OPENALEX_WORKS_EMPTY})
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(name="Test", provider="openalex", query_json={"source_id": "S999"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)
    _assert_eq("count=0", result.sample_count, 0)


def test_openalex_verify_concept_id() -> None:
    from providers.openalex import OpenAlexProvider
    client = _mock_async_client({"works": OPENALEX_WORKS_WITH_RESULTS})
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(name="ML", provider="openalex", query_json={"concept_id": "C123"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)


def test_openalex_verify_no_known_key() -> None:
    from providers.openalex import OpenAlexProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(name="X", provider="openalex", query_json={"unknown": "x"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


def test_openalex_user_agent() -> None:
    from providers.openalex import OPENALEX_USER_AGENT
    _assert_in("mailto:", "mailto:", OPENALEX_USER_AGENT)
    _assert_in("Basira", "Basira", OPENALEX_USER_AGENT)


def test_openalex_rate_limit() -> None:
    from providers.openalex import OPENALEX_RATE_LIMIT_SECONDS
    _assert_true("positive", OPENALEX_RATE_LIMIT_SECONDS > 0)


# ══════════════════════════════════════════════════════════════════════════════
# 3. CrossrefProvider tests
# ══════════════════════════════════════════════════════════════════════════════

CROSSREF_WORKS_RESPONSE = {
    "message": {
        "items": [
            {"DOI": "10.1234/test", "title": ["Test Paper"]},
            {"DOI": "10.5678/demo", "title": ["Demo Paper"]},
        ],
    },
}
CROSSREF_DOI_RESPONSE = {
    "status": "ok",
    "message": {"title": ["Test Paper"], "DOI": "10.1234/test"},
}


def test_crossref_provider_id() -> None:
    from providers.crossref import CrossrefProvider
    _assert_eq("provider_id", CrossrefProvider.provider_id, "crossref")


def test_crossref_resolve_returns_results() -> None:
    from providers.crossref import CrossrefProvider
    client = _mock_async_client({"works": CROSSREF_WORKS_RESPONSE})
    provider = CrossrefProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="machine learning")))
    _assert_true("has results", len(results) > 0)
    for r in results:
        _assert_eq("provider=crossref", r.provider, "crossref")
        _assert_true("has doi", "doi" in r.query_json)
        _assert_true("has provenance_url", bool(r.provenance_url))


def test_crossref_resolve_empty_returns_empty() -> None:
    from providers.crossref import CrossrefProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = CrossrefProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="")))
    _assert_eq("empty", results, [])


def test_crossref_verify_valid() -> None:
    from providers.crossref import CrossrefProvider
    client = _mock_async_client({"works": CROSSREF_DOI_RESPONSE})
    provider = CrossrefProvider(client=client)
    source = ResolvedSource(name="Test", provider="crossref", query_json={"doi": "10.1234/test"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)
    _assert_eq("count=1", result.sample_count, 1)


def test_crossref_verify_no_doi() -> None:
    from providers.crossref import CrossrefProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = CrossrefProvider(client=client)
    source = ResolvedSource(name="X", provider="crossref", query_json={"query": "no doi"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


# ══════════════════════════════════════════════════════════════════════════════
# 4. ArxivProvider tests
# ══════════════════════════════════════════════════════════════════════════════

ARXIV_XML_WITH_RESULTS = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>42</opensearch:totalResults>
  <entry><id>http://arxiv.org/abs/2401.00001</id><title>Test Paper</title></entry>
</feed>"""
ARXIV_XML_EMPTY = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>0</opensearch:totalResults>
</feed>"""


def test_arxiv_provider_id() -> None:
    _assert_eq("provider_id", ArxivProvider.provider_id, "arxiv")


def test_arxiv_resolve_physics_includes_non_cs() -> None:
    from providers.arxiv import ArxivProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = ArxivProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="physics")))
    cats = [r.query_json.get("search_query", "") for r in results]
    has_physics = any("physics.gen-ph" in c for c in cats)
    _assert_true("physics category found", has_physics)
    has_non_cs = any(not c.startswith("cs:") and "cs." not in c.split("cat:")[-1].split("+")[0] for c in cats)
    _assert_true("non-CS category present", has_non_cs)


def test_arxiv_resolve_biology_categories() -> None:
    from providers.arxiv import ArxivProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = ArxivProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="biology")))
    cats = [r.query_json.get("search_query", "") for r in results]
    has_qbio = any("q-bio" in c for c in cats)
    _assert_true("q-bio category found", has_qbio)


def test_arxiv_resolve_default_to_cs() -> None:
    from providers.arxiv import ArxivProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = ArxivProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="unknown_topic_xyz")))
    cats = [r.query_json.get("search_query", "") for r in results]
    has_default = any("cs.AI" in c for c in cats)
    _assert_true("defaults to cs.AI", has_default)


def test_arxiv_resolve_empty_query() -> None:
    from providers.arxiv import ArxivProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = ArxivProvider(client=client)
    _assert_eq("empty", _run_async(provider.resolve(SourceIntent(query=""))), [])


def test_arxiv_verify_with_results() -> None:
    from providers.arxiv import ArxivProvider
    client = MagicMock()
    client.get = AsyncMock()
    client.get.return_value = MagicMock(status_code=200, text=ARXIV_XML_WITH_RESULTS)
    provider = ArxivProvider(client=client)
    source = ResolvedSource(name="arXiv cs.AI", provider="arxiv", query_json={"search_query": "cat:cs.AI"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)
    _assert_true("count>0", result.sample_count > 0)


def test_arxiv_verify_empty() -> None:
    from providers.arxiv import ArxivProvider
    client = MagicMock()
    client.get = AsyncMock()
    client.get.return_value = MagicMock(status_code=200, text=ARXIV_XML_EMPTY)
    provider = ArxivProvider(client=client)
    source = ResolvedSource(name="arXiv unknown", provider="arxiv", query_json={"search_query": "cat:cs.OBSCURE"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


def test_arxiv_category_map_structure() -> None:
    _assert_true("has physics", "physics" in ARXIV_CATEGORY_MAP)
    _assert_true("has biology", "biology" in ARXIV_CATEGORY_MAP)
    _assert_true("has computer_science", "computer_science" in ARXIV_CATEGORY_MAP)
    for cat in ARXIV_CATEGORY_MAP["biology"]:
        _assert_true(f"biology cat {cat} starts with q-bio", cat.startswith("q-bio"))


# ══════════════════════════════════════════════════════════════════════════════
# 5. GenericRSSProvider tests
# ══════════════════════════════════════════════════════════════════════════════

RSS_BODY = '<rss version="2.0"><channel><title>Test Feed</title><item><title>Article</title></item></channel></rss>'
ATOM_BODY = '<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Feed</title><entry><title>Entry</title></entry></feed>'
NOT_A_FEED = "<html><body><h1>Not a feed</h1></body></html>"


def test_generic_rss_provider_id() -> None:
    from providers.generic_rss import GenericRSSProvider
    _assert_eq("provider_id", GenericRSSProvider.provider_id, "rss")


def test_generic_rss_resolve_returns_url() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = GenericRSSProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="https://example.com/feed.xml")))
    _assert_eq("one result", len(results), 1)
    _assert_eq("provider=rss", results[0].provider, "rss")
    _assert_eq("has url", results[0].query_json.get("url"), "https://example.com/feed.xml")


def test_generic_rss_resolve_empty() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = GenericRSSProvider(client=client)
    _assert_eq("empty", _run_async(provider.resolve(SourceIntent(query=""))), [])


def test_generic_rss_verify_valid_rss() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = MagicMock()
    resp = MagicMock(status_code=200, text=RSS_BODY)
    client.get = AsyncMock(return_value=resp)
    mock_check = MagicMock()
    with patch("providers.generic_rss.check_url", mock_check):
        provider = GenericRSSProvider(client=client)
        source = ResolvedSource(name="Test", provider="rss", query_json={"url": "https://example.com/feed.xml"})
        result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)
    mock_check.assert_called_once_with("https://example.com/feed.xml")


def test_generic_rss_verify_valid_atom() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = MagicMock()
    resp = MagicMock(status_code=200, text=ATOM_BODY)
    client.get = AsyncMock(return_value=resp)
    with patch("providers.generic_rss.check_url"):
        provider = GenericRSSProvider(client=client)
        source = ResolvedSource(name="Test", provider="rss", query_json={"url": "https://example.com/atom.xml"})
        result = _run_async(provider.verify(source))
    _assert_eq("atom verified=True", result.verified, True)


def test_generic_rss_verify_not_a_feed() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = MagicMock()
    resp = MagicMock(status_code=200, text=NOT_A_FEED)
    client.get = AsyncMock(return_value=resp)
    with patch("providers.generic_rss.check_url"):
        provider = GenericRSSProvider(client=client)
        source = ResolvedSource(name="Test", provider="rss", query_json={"url": "https://example.com/page.html"})
        result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)
    _assert_in("message", "not a feed", result.message or "")


def test_generic_rss_verify_ssrf_blocked() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = GenericRSSProvider(client=client)
    source = ResolvedSource(name="Test", provider="rss", query_json={"url": "http://10.0.0.1/feed.xml"})
    with patch("providers.generic_rss.check_url", side_effect=net_guard.SSRFBlockedError("blocked")):
        result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)
    _assert_in("message", "SSRF blocked", result.message or "")


def test_generic_rss_verify_no_url() -> None:
    from providers.generic_rss import GenericRSSProvider
    client = _mock_async_client({}, fail_on_extra=False)
    with patch("providers.generic_rss.check_url"):
        provider = GenericRSSProvider(client=client)
        source = ResolvedSource(name="X", provider="rss", query_json={})
        result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


# ══════════════════════════════════════════════════════════════════════════════
# 6. DOAJProvider tests
# ══════════════════════════════════════════════════════════════════════════════

DOAJ_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "abc123",
            "bibjson": {"title": "Journal of Law & Society", "pissn": "1234-5678", "eissn": "8765-4321", "active": True},
        },
        {
            "id": "def456",
            "bibjson": {"title": "Law Review Quarterly", "pissn": "1111-2222", "active": True},
        },
    ],
}
DOAJ_JOURNAL_RESPONSE = {
    "bibjson": {"active": True, "title": "Journal of Law & Society"},
    "last_updated_timestamp": 1700000000000,
}


def test_doaj_provider_id() -> None:
    from providers.doaj import DoajProvider
    _assert_eq("provider_id", DoajProvider.provider_id, "doaj")


def test_doaj_resolve_law_intent_returns_results() -> None:
    from providers.doaj import DoajProvider
    client = _mock_async_client({"search/journals": DOAJ_SEARCH_RESPONSE})
    provider = DoajProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="law")))
    _assert_true("has results", len(results) > 0)
    for r in results:
        _assert_eq("provider=doaj", r.provider, "doaj")
        _assert_true("has issn", bool(r.query_json.get("issn")))
        _assert_true("has provenance_url", bool(r.provenance_url))


def test_doaj_verify_active_journal() -> None:
    from providers.doaj import DoajProvider
    client = _mock_async_client({"journals": DOAJ_JOURNAL_RESPONSE})
    provider = DoajProvider(client=client)
    source = ResolvedSource(name="Test", provider="doaj", query_json={"journal_id": "abc123"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)


def test_doaj_verify_no_journal_id() -> None:
    from providers.doaj import DoajProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = DoajProvider(client=client)
    source = ResolvedSource(name="X", provider="doaj", query_json={})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


# ══════════════════════════════════════════════════════════════════════════════
# 7. HAL provider tests
# ══════════════════════════════════════════════════════════════════════════════

HAL_SEARCH_RESPONSE = {
    "response": {
        "numFound": 10,
        "docs": [
            {"docid": "hal-001234", "label_s": "HAL Computer Science", "title_s": ["CS Paper"]},
            {"docid": "hal-005678", "label_s": "HAL Physics", "title_s": ["Physics Paper"]},
        ],
    },
}
HAL_VERIFY_RESPONSE = {"response": {"numFound": 5}}


def test_hal_provider_id() -> None:
    from providers.hal import HalProvider
    _assert_eq("provider_id", HalProvider.provider_id, "hal")


def test_hal_resolve_returns_results() -> None:
    from providers.hal import HalProvider
    client = _mock_async_client({"search/": HAL_SEARCH_RESPONSE})
    provider = HalProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="computer science")))
    _assert_true("has results", len(results) > 0)
    for r in results:
        _assert_eq("provider=hal", r.provider, "hal")
        _assert_true("has docid", bool(r.query_json.get("docid")))


def test_hal_verify_valid() -> None:
    from providers.hal import HalProvider
    client = _mock_async_client({"search/": HAL_VERIFY_RESPONSE})
    provider = HalProvider(client=client)
    source = ResolvedSource(name="Test", provider="hal", query_json={"docid": "hal-001234"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)
    _assert_eq("count=5", result.sample_count, 5)


def test_hal_verify_no_docid() -> None:
    from providers.hal import HalProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = HalProvider(client=client)
    source = ResolvedSource(name="X", provider="hal", query_json={})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


# ══════════════════════════════════════════════════════════════════════════════
# 8. DBLP provider tests
# ══════════════════════════════════════════════════════════════════════════════

DBLP_SEARCH_RESPONSE = {
    "result": {
        "hits": {
            "hit": [
                {
                    "info": {
                        "title": "Deep Learning in NLP",
                        "venue": "ACL",
                        "year": "2024",
                        "url": "https://dblp.org/rec/conf/acl/2024",
                    },
                },
                {
                    "info": {
                        "title": "Transformers for Vision",
                        "venue": "CVPR",
                        "year": "2024",
                        "url": "https://dblp.org/rec/conf/cvpr/2024",
                    },
                },
            ],
        },
    },
}


def test_dblp_provider_id() -> None:
    from providers.dblp import DblpProvider
    _assert_eq("provider_id", DblpProvider.provider_id, "dblp")


def test_dblp_resolve_returns_results() -> None:
    from providers.dblp import DblpProvider
    client = _mock_async_client({"search/publ/api": DBLP_SEARCH_RESPONSE})
    provider = DblpProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="deep learning")))
    _assert_true("has results", len(results) > 0)
    for r in results:
        _assert_eq("provider=dblp", r.provider, "dblp")
        _assert_true("has name", bool(r.name))


def test_dblp_verify_valid() -> None:
    from providers.dblp import DblpProvider
    client = MagicMock()
    resp = MagicMock(status_code=200)
    client.get = AsyncMock(return_value=resp)
    provider = DblpProvider(client=client)
    source = ResolvedSource(name="Test", provider="dblp", query_json={"url": "https://dblp.org/rec/conf/acl/2024"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)


def test_dblp_verify_no_url() -> None:
    from providers.dblp import DblpProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = DblpProvider(client=client)
    source = ResolvedSource(name="X", provider="dblp", query_json={})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


# ══════════════════════════════════════════════════════════════════════════════
# 9. OpenReview provider tests
# ══════════════════════════════════════════════════════════════════════════════

OPENREVIEW_VENUES_RESPONSE = {
    "venues": [
        {"id": "ICLR.cc/2025/Conference"},
        {"id": "NeurIPS.cc/2025/Conference"},
        {"id": "COLM/2025/Conference"},
    ],
}
OPENREVIEW_NOTES_RESPONSE = {
    "count": 15,
    "notes": [{"id": "note1", "content": {"title": {"value": "Test Paper"}}}],
}


def test_openreview_provider_id() -> None:
    from providers.openreview import OpenReviewProvider
    _assert_eq("provider_id", OpenReviewProvider.provider_id, "openreview")


def test_openreview_resolve_matches_query() -> None:
    from providers.openreview import OpenReviewProvider
    client = _mock_async_client({"venues": OPENREVIEW_VENUES_RESPONSE})
    provider = OpenReviewProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="ICLR")))
    _assert_true("has results", len(results) > 0)
    for r in results:
        _assert_eq("provider=openreview", r.provider, "openreview")
        _assert_true("has invitation", bool(r.query_json.get("invitation")))


def test_openreview_resolve_no_match() -> None:
    from providers.openreview import OpenReviewProvider
    client = _mock_async_client({"venues": OPENREVIEW_VENUES_RESPONSE})
    provider = OpenReviewProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="CVPR")))
    _assert_eq("no match", len(results), 0)


def test_openreview_verify_valid() -> None:
    from providers.openreview import OpenReviewProvider
    client = _mock_async_client({"notes": OPENREVIEW_NOTES_RESPONSE})
    provider = OpenReviewProvider(client=client)
    source = ResolvedSource(name="ICLR", provider="openreview", query_json={"invitation": "ICLR.cc/2025/Conference"})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=True", result.verified, True)
    _assert_true("count>0", result.sample_count > 0)


def test_openreview_verify_no_invitation() -> None:
    from providers.openreview import OpenReviewProvider
    client = _mock_async_client({}, fail_on_extra=False)
    provider = OpenReviewProvider(client=client)
    source = ResolvedSource(name="X", provider="openreview", query_json={})
    result = _run_async(provider.verify(source))
    _assert_eq("verified=False", result.verified, False)


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# Story 12.6 — fetch() tests
# ══════════════════════════════════════════════════════════════════════════════


def test_provider_fetch_base_returns_empty():
    """SourceProvider.fetch() default returns empty list."""
    class _TestProvider(SourceProvider):
        provider_id = "test"
        async def resolve(self, intent): return []
        async def verify(self, source): return VerifiedSource(verified=True)
    p = _TestProvider()
    src = ResolvedSource(name="x", provider="test", query_json={})
    result = _run_async(p.fetch(src))
    _assert_true("fetch_base_returns_empty", isinstance(result, list) and len(result) == 0)


def test_generic_rss_fetch_returns_fetched_articles():
    """GenericRSSProvider.fetch() returns FetchedArticle list from RSS XML."""
    rss_xml = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <guid>https://example.com/1</guid>
      <title>First Article</title>
      <link>https://example.com/1</link>
      <description>Summary 1</description>
      <author>Author A</author>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
    <item>
      <guid>https://example.com/2</guid>
      <title>Second Article</title>
      <link>https://example.com/2</link>
      <description>Summary 2</description>
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    client = MagicMock()
    client.get = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = rss_xml
    client.get.return_value = resp

    from providers.generic_rss import GenericRSSProvider
    p = GenericRSSProvider(client=client)
    src = ResolvedSource(name="test-feed", provider="rss", query_json={"url": "https://example.com/feed"})

    # Patch check_url to bypass SSRF guard for test
    with patch.object(p, "_get_client", return_value=client):
        result = _run_async(p.fetch(src))

    _assert_true("rss_fetch_returns_list", isinstance(result, list))
    _assert_eq("rss_fetch_len", len(result), 2)
    if len(result) >= 2:
        _assert_eq("rss_fetch_title_1", result[0].title, "First Article")
        _assert_eq("rss_fetch_url_1", result[0].url, "https://example.com/1")
        _assert_eq("rss_fetch_summary_1", result[0].summary, "Summary 1")
        _assert_eq("rss_fetch_author_1", result[0].author, "Author A")
        _assert_eq("rss_fetch_title_2", result[1].title, "Second Article")


def test_generic_rss_fetch_no_url_returns_empty():
    """GenericRSSProvider.fetch() returns empty list when no URL."""
    from providers.generic_rss import GenericRSSProvider
    p = GenericRSSProvider()
    src = ResolvedSource(name="x", provider="rss", query_json={})
    result = _run_async(p.fetch(src))
    _assert_true("rss_fetch_no_url_empty", result == [])


def test_generic_rss_fetch_http_error_returns_empty():
    """GenericRSSProvider.fetch() returns empty on HTTP error."""
    client = MagicMock()
    client.get = AsyncMock()
    resp = MagicMock()
    resp.status_code = 500
    resp.text = ""
    client.get.return_value = resp

    from providers.generic_rss import GenericRSSProvider
    p = GenericRSSProvider(client=client)
    src = ResolvedSource(name="x", provider="rss", query_json={"url": "https://example.com/feed"})

    with patch.object(p, "_get_client", return_value=client):
        result = _run_async(p.fetch(src))

    _assert_true("rss_fetch_http_error_empty", result == [])


def test_arxiv_fetch_returns_fetched_articles():
    """ArxivProvider.fetch() returns FetchedArticle list from arXiv Atom API."""
    atom_xml = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <entry>
    <id>http://arxiv.org/abs/2401.00001</id>
    <title>Test Paper One</title>
    <summary>Abstract of paper one</summary>
    <author><name>Alice</name></author>
    <published>2024-01-01T00:00:00Z</published>
    <link href="http://arxiv.org/abs/2401.00001" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002</id>
    <title>Test Paper Two</title>
    <summary>Abstract of paper two</summary>
    <author><name>Bob</name></author>
    <published>2024-01-02T00:00:00Z</published>
    <link href="http://arxiv.org/abs/2401.00002" rel="alternate" type="text/html"/>
  </entry>
</feed>"""

    client = MagicMock()
    client.get = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = atom_xml
    client.get.return_value = resp

    p = ArxivProvider(client=client)
    src = ResolvedSource(name="arxiv cs.AI", provider="arxiv", query_json={"search_query": "cat:cs.AI"})

    with patch.object(p, "_get_client", return_value=client):
        result = _run_async(p.fetch(src))

    _assert_true("arxiv_fetch_returns_list", isinstance(result, list))
    _assert_eq("arxiv_fetch_len", len(result), 2)
    if len(result) >= 2:
        _assert_eq("arxiv_fetch_title_1", result[0].title, "Test Paper One")
        _assert_in("arxiv_fetch_url_1", "2401.00001", result[0].url)
        _assert_eq("arxiv_fetch_author_1", result[0].author, "Alice")
        _assert_eq("arxiv_fetch_title_2", result[1].title, "Test Paper Two")


def test_arxiv_fetch_no_search_query_returns_empty():
    """ArxivProvider.fetch() returns empty list with no search_query."""
    p = ArxivProvider()
    src = ResolvedSource(name="x", provider="arxiv", query_json={})
    result = _run_async(p.fetch(src))
    _assert_true("arxiv_fetch_empty_query", result == [])


def test_arxiv_fetch_http_error_returns_empty():
    """ArxivProvider.fetch() returns empty list on HTTP error."""
    client = MagicMock()
    client.get = AsyncMock()
    resp = MagicMock()
    resp.status_code = 500
    resp.text = ""
    client.get.return_value = resp

    p = ArxivProvider(client=client)
    src = ResolvedSource(name="x", provider="arxiv", query_json={"search_query": "cat:cs.AI"})

    with patch.object(p, "_get_client", return_value=client):
        result = _run_async(p.fetch(src))

    _assert_true("arxiv_fetch_http_error_empty", result == [])


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


def _sorted() -> list[str]:
    """Return list of test function names in desired order."""
    return [
        # 1. Base
        "test_base_models",
        "test_source_provider_abc",
        "test_provider_registry_contains_all",
        # 2. OpenAlex
        "test_openalex_provider_id",
        "test_openalex_resolve_returns_results",
        "test_openalex_resolve_empty_query_returns_empty",
        "test_openalex_verify_returns_verified_true",
        "test_openalex_verify_returns_false_when_empty",
        "test_openalex_verify_concept_id",
        "test_openalex_verify_no_known_key",
        "test_openalex_user_agent",
        "test_openalex_rate_limit",
        # 3. Crossref
        "test_crossref_provider_id",
        "test_crossref_resolve_returns_results",
        "test_crossref_resolve_empty_returns_empty",
        "test_crossref_verify_valid",
        "test_crossref_verify_no_doi",
        # 4. Arxiv
        "test_arxiv_provider_id",
        "test_arxiv_resolve_physics_includes_non_cs",
        "test_arxiv_resolve_biology_categories",
        "test_arxiv_resolve_default_to_cs",
        "test_arxiv_resolve_empty_query",
        "test_arxiv_verify_with_results",
        "test_arxiv_verify_empty",
        "test_arxiv_category_map_structure",
        # 5. GenericRSS
        "test_generic_rss_provider_id",
        "test_generic_rss_resolve_returns_url",
        "test_generic_rss_resolve_empty",
        "test_generic_rss_verify_valid_rss",
        "test_generic_rss_verify_valid_atom",
        "test_generic_rss_verify_not_a_feed",
        "test_generic_rss_verify_ssrf_blocked",
        "test_generic_rss_verify_no_url",
        # 6. DOAJ
        "test_doaj_provider_id",
        "test_doaj_resolve_law_intent_returns_results",
        "test_doaj_verify_active_journal",
        "test_doaj_verify_no_journal_id",
        # 7. HAL
        "test_hal_provider_id",
        "test_hal_resolve_returns_results",
        "test_hal_verify_valid",
        "test_hal_verify_no_docid",
        # 8. DBLP
        "test_dblp_provider_id",
        "test_dblp_resolve_returns_results",
        "test_dblp_verify_valid",
        "test_dblp_verify_no_url",
        # 9. OpenReview
        "test_openreview_provider_id",
        "test_openreview_resolve_matches_query",
        "test_openreview_resolve_no_match",
        "test_openreview_verify_valid",
        "test_openreview_verify_no_invitation",
        # 10. Story 12.6 — fetch()
        "test_provider_fetch_base_returns_empty",
        "test_generic_rss_fetch_returns_fetched_articles",
        "test_generic_rss_fetch_no_url_returns_empty",
        "test_generic_rss_fetch_http_error_returns_empty",
        "test_arxiv_fetch_returns_fetched_articles",
        "test_arxiv_fetch_no_search_query_returns_empty",
        "test_arxiv_fetch_http_error_returns_empty",
    ]


if __name__ == "__main__":
    names = _sorted()
    for name in names:
        fn = globals().get(name)
        if fn:
            fn()

    total = _PASS + _FAIL
    print(f"\n{'='*40}")
    print(f"  {_PASS}/{total} passed")
    if _FAIL:
        print(f"  \u274c  {_FAIL} FAILED")
        sys.exit(1)
    else:
        print(f"  \u2705  ALL PASSED")
