"""
Tests for Story 12.3 — OpenAlexProvider and CrossrefProvider.

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
if _extractor_dir not in sys.path:
    sys.path.insert(0, _extractor_dir)

from providers.base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource

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


# ── Fixtures ──────────────────────────────────────────────────────────────────

_OPENALEX_SOURCES_RESPONSE = {
    "results": [
        {"id": "https://openalex.org/S123", "display_name": "Journal of AI Research", "type": "journal"},
        {"id": "https://openalex.org/S456", "display_name": "Machine Learning Review", "type": "journal"},
    ],
}

_OPENALEX_CONCEPTS_RESPONSE = {
    "results": [
        {"id": "https://openalex.org/C123", "display_name": "Machine Learning", "type": "concept"},
    ],
}

_OPENALEX_WORKS_RESPONSE_WITH_RESULTS = {
    "meta": {"count": 42, "db_response_time_ms": 5, "page": 1, "per_page": 1},
}

_OPENALEX_WORKS_RESPONSE_EMPTY = {
    "meta": {"count": 0, "db_response_time_ms": 3, "page": 1, "per_page": 1},
}

_CROSSREF_WORKS_RESPONSE = {
    "message": {
        "items": [
            {"DOI": "10.1234/ai-research", "title": ["Advances in AI Research"]},
            {"DOI": "10.5678/ml-review", "title": ["Machine Learning Review"]},
        ],
    },
}


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
                return resp
        if fail_on_extra:
            raise AssertionError(f"Unexpected URL: {url}")
        resp = MagicMock()
        resp.status_code = 404
        resp.json = MagicMock(return_value={})
        return resp

    client.get.side_effect = side_effect
    return client


# ══════════════════════════════════════════════════════════════════════════════
# Base model tests
# ══════════════════════════════════════════════════════════════════════════════

def test_base_models() -> None:
    si = SourceIntent(query="machine learning", category="research")
    _assert_eq("SourceIntent query", si.query, "machine learning")
    _assert_eq("SourceIntent category", si.category, "research")
    _assert_eq("SourceIntent filters default", si.filters, {})

    rs = ResolvedSource(name="Test", provider="openalex", query_json={"key": "val"})
    _assert_eq("ResolvedSource name", rs.name, "Test")
    _assert_eq("ResolvedSource provider", rs.provider, "openalex")
    _assert_eq("ResolvedSource label default", rs.label, "")
    _assert_eq("ResolvedSource category default", rs.category, "")

    vs = VerifiedSource(verified=True, sample_count=10)
    _assert_eq("VerifiedSource verified=True", vs.verified, True)
    _assert_eq("VerifiedSource sample_count", vs.sample_count, 10)
    _assert_eq("VerifiedSource message default", vs.message, "")


def test_source_provider_abc() -> None:
    _assert_true("SourceProvider has provider_id", hasattr(SourceProvider, "provider_id"))
    _assert_true("SourceProvider has resolve", hasattr(SourceProvider, "resolve"))
    _assert_true("SourceProvider has verify", hasattr(SourceProvider, "verify"))


# ══════════════════════════════════════════════════════════════════════════════
# OpenAlexProvider tests
# ══════════════════════════════════════════════════════════════════════════════

def test_openalex_provider_id() -> None:
    from providers.openalex import OpenAlexProvider
    _assert_eq("OpenAlexProvider.provider_id", OpenAlexProvider.provider_id, "openalex")


def test_openalex_resolve_returns_resolved_sources() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({
        "sources": _OPENALEX_SOURCES_RESPONSE,
        "concepts": _OPENALEX_CONCEPTS_RESPONSE,
    })
    provider = OpenAlexProvider(client=client)
    intent = SourceIntent(query="machine learning")
    results = _run_async(provider.resolve(intent))

    _assert_true("returns list", isinstance(results, list))
    _assert_true("returns results", len(results) > 0)

    for r in results:
        _assert_eq(f"provider openalex for {r.name}", r.provider, "openalex")
        _assert_true(f"name non-empty for {r.name}", bool(r.name))
        _assert_true(f"query_json non-empty for {r.name}", bool(r.query_json))
        _assert_true(f"label non-empty for {r.name}", bool(r.label))


def test_openalex_resolve_sources_have_source_id() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({
        "sources": _OPENALEX_SOURCES_RESPONSE,
        "concepts": _OPENALEX_CONCEPTS_RESPONSE,
    })
    provider = OpenAlexProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="machine learning")))

    journal_sources = [r for r in results if r.label == "journal"]
    _assert_true("has journal sources", len(journal_sources) > 0)
    _assert_in("query_json has source_id", "source_id", json.dumps(journal_sources[0].query_json))


def test_openalex_resolve_empty_query() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({}, fail_on_extra=False)
    provider = OpenAlexProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="  ")))
    _assert_eq("empty query returns []", results, [])


def test_openalex_verify_returns_verified_true() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({
        "works": _OPENALEX_WORKS_RESPONSE_WITH_RESULTS,
    })
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(
        name="Journal of AI Research",
        provider="openalex",
        query_json={"source_id": "https://openalex.org/S123", "search": "ai"},
        label="journal",
        provenance_url="https://openalex.org/S123",
    )
    result = _run_async(provider.verify(source))

    _assert_eq("verified=True", result.verified, True)
    _assert_true("sample_count > 0", result.sample_count > 0)
    _assert_eq("sample_count=42", result.sample_count, 42)


def test_openalex_verify_returns_verified_false_when_empty() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({
        "works": _OPENALEX_WORKS_RESPONSE_EMPTY,
    })
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(
        name="Obscure Journal",
        provider="openalex",
        query_json={"source_id": "https://openalex.org/S999", "search": "obscure"},
        label="journal",
        provenance_url="https://openalex.org/S999",
    )
    result = _run_async(provider.verify(source))

    _assert_eq("verified=False when empty", result.verified, False)
    _assert_eq("sample_count=0 when empty", result.sample_count, 0)


def test_openalex_verify_concept_id() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({
        "works": _OPENALEX_WORKS_RESPONSE_WITH_RESULTS,
    })
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(
        name="Machine Learning",
        provider="openalex",
        query_json={"concept_id": "https://openalex.org/C123", "search": "ml"},
        label="concept",
        provenance_url="https://openalex.org/C123",
    )
    result = _run_async(provider.verify(source))
    _assert_eq("verify by concept_id returns verified=True", result.verified, True)


def test_openalex_verify_no_known_key() -> None:
    from providers.openalex import OpenAlexProvider

    client = _mock_async_client({}, fail_on_extra=False)
    provider = OpenAlexProvider(client=client)
    source = ResolvedSource(
        name="Unknown",
        provider="openalex",
        query_json={"unknown_key": "xxx"},
    )
    result = _run_async(provider.verify(source))
    _assert_eq("verify with unknown key returns verified=False", result.verified, False)


def test_openalex_user_agent_header() -> None:
    from providers.openalex import OPENALEX_USER_AGENT
    _assert_in("User-Agent has mailto:", "mailto:", OPENALEX_USER_AGENT)
    _assert_in("User-Agent has Basira", "Basira", OPENALEX_USER_AGENT)


def test_openalex_rate_limit_constant() -> None:
    from providers.openalex import OPENALEX_RATE_LIMIT_SECONDS
    _assert_true("rate limit is positive", OPENALEX_RATE_LIMIT_SECONDS > 0)
    _assert_true("rate limit <= 1.0", OPENALEX_RATE_LIMIT_SECONDS <= 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# CrossrefProvider tests
# ══════════════════════════════════════════════════════════════════════════════

def test_crossref_provider_id() -> None:
    from providers.crossref import CrossrefProvider
    _assert_eq("CrossrefProvider.provider_id", CrossrefProvider.provider_id, "crossref")


def test_crossref_resolve_returns_resolved_sources() -> None:
    from providers.crossref import CrossrefProvider

    client = _mock_async_client({
        "works": _CROSSREF_WORKS_RESPONSE,
    })
    provider = CrossrefProvider(client=client)
    intent = SourceIntent(query="machine learning")
    results = _run_async(provider.resolve(intent))

    _assert_true("returns list", isinstance(results, list))
    _assert_true("returns results", len(results) > 0)

    for r in results:
        _assert_eq(f"provider crossref for {r.name}", r.provider, "crossref")
        _assert_true(f"name non-empty for {r.name}", bool(r.name))
        _assert_true(f"query_json non-empty for {r.name}", bool(r.query_json))


def test_crossref_resolve_has_doi_in_query_json() -> None:
    from providers.crossref import CrossrefProvider

    client = _mock_async_client({
        "works": _CROSSREF_WORKS_RESPONSE,
    })
    provider = CrossrefProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="machine learning")))

    for r in results:
        _assert_true(f"query_json has doi for {r.name}", "doi" in r.query_json)
        _assert_true(f"provenance_url for {r.name}", r.provenance_url.startswith("https://doi.org/"))


def test_crossref_resolve_empty_query() -> None:
    from providers.crossref import CrossrefProvider

    client = _mock_async_client({}, fail_on_extra=False)
    provider = CrossrefProvider(client=client)
    results = _run_async(provider.resolve(SourceIntent(query="")))
    _assert_eq("empty query returns []", results, [])


def test_crossref_verify_valid_doi() -> None:
    from providers.crossref import CrossrefProvider

    crossref_work_response = {
        "status": "ok",
        "message": {"title": ["Advances in AI Research"], "DOI": "10.1234/ai-research"},
    }

    client = _mock_async_client({"works": crossref_work_response})
    provider = CrossrefProvider(client=client)
    source = ResolvedSource(
        name="Advances in AI Research",
        provider="crossref",
        query_json={"doi": "10.1234/ai-research", "query": "ai"},
        label="article",
        provenance_url="https://doi.org/10.1234/ai-research",
    )
    result = _run_async(provider.verify(source))

    _assert_eq("verified=True", result.verified, True)
    _assert_eq("sample_count=1", result.sample_count, 1)
    _assert_eq("message='DOI resolved'", result.message, "DOI resolved")


def test_crossref_verify_no_doi() -> None:
    from providers.crossref import CrossrefProvider

    client = _mock_async_client({}, fail_on_extra=False)
    provider = CrossrefProvider(client=client)
    source = ResolvedSource(
        name="Unknown",
        provider="crossref",
        query_json={"query": "no doi here"},
    )
    result = _run_async(provider.verify(source))
    _assert_eq("no DOI returns verified=False", result.verified, False)


def test_crossref_fetch_crossref_work_helper() -> None:
    from providers.crossref import fetch_crossref_work

    crossref_work_response = {
        "status": "ok",
        "message": {"title": ["Test Paper"], "DOI": "10.9999/test"},
    }

    client = _mock_async_client({"works": crossref_work_response})
    result = _run_async(fetch_crossref_work("10.9999/test", client))
    _assert_true("fetch_crossref_work returns dict", isinstance(result, dict))
    _assert_eq("has title", result.get("title"), ["Test Paper"])


# ══════════════════════════════════════════════════════════════════════════════
# Rate-limit integration test
# ══════════════════════════════════════════════════════════════════════════════

def test_openalex_rate_limiting_respects_sleep() -> None:
    from providers.openalex import _openalex_rate_limited_get, _openalex_last_call, OPENALEX_RATE_LIMIT_SECONDS

    # Reset global state
    import providers.openalex as oa_mod
    oa_mod._openalex_last_call = 0.0
    # But last_call is a module global; we'll test via the sleep mechanism instead

    client = MagicMock()
    client.get = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={})
    client.get.return_value = resp

    # First call should pass immediately
    t0 = time.monotonic()
    result = _run_async(_openalex_rate_limited_get(client, "https://example.com/test"))
    dt1 = time.monotonic() - t0
    _assert_true("first call is fast (<0.05s)", dt1 < 0.05)
    _assert_true("first call returns response", result is not None)

    # Second call should be rate-limited (sleep for RATE_LIMIT_SECONDS)
    t1 = time.monotonic()
    result2 = _run_async(_openalex_rate_limited_get(client, "https://example.com/test2"))
    dt2 = time.monotonic() - t1
    _assert_true("second call is rate-limited", dt2 >= OPENALEX_RATE_LIMIT_SECONDS * 0.9)
    _assert_true("second call returns response", result2 is not None)


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


if __name__ == "__main__":
    test_base_models()
    test_source_provider_abc()
    test_openalex_provider_id()
    test_openalex_resolve_returns_resolved_sources()
    test_openalex_resolve_sources_have_source_id()
    test_openalex_resolve_empty_query()
    test_openalex_verify_returns_verified_true()
    test_openalex_verify_returns_verified_false_when_empty()
    test_openalex_verify_concept_id()
    test_openalex_verify_no_known_key()
    test_openalex_user_agent_header()
    test_openalex_rate_limit_constant()
    test_crossref_provider_id()
    test_crossref_resolve_returns_resolved_sources()
    test_crossref_resolve_has_doi_in_query_json()
    test_crossref_resolve_empty_query()
    test_crossref_verify_valid_doi()
    test_crossref_verify_no_doi()
    test_crossref_fetch_crossref_work_helper()
    test_openalex_rate_limiting_respects_sleep()

    total = _PASS + _FAIL
    print(f"\n{'='*40}")
    print(f"  {_PASS}/{total} passed")
    if _FAIL:
        print(f"  \u274c  {_FAIL} FAILED")
        sys.exit(1)
    else:
        print(f"  \u2705  ALL PASSED")
