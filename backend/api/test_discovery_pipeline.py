"""Tests for source_discovery.py RESOLVE/VERIFY/RANK pipeline (Story 13-2)."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

_api_dir = os.path.join(os.path.dirname(__file__))
_extractor_dir = os.path.join(_api_dir, "..", "extractor")
for p in [_api_dir, _extractor_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from services.source_discovery import (
    DiscoveryCandidate,
    DiscoveryPack,
    DiscoveredItem,
    ExpandResult,
    _cap_candidates,
    _rank_and_group,
    cache_clear,
    resolve_verify_rank,
)


def _make_candidate(name: str, provider: str = "openalex", score: float = 1.0, label: str = "", provenance_url: str = "") -> DiscoveryCandidate:
    return DiscoveryCandidate(name=name, provider=provider, relevance_score=score, label=label, provenance_url=provenance_url)


def _make_result(**kwargs) -> ExpandResult:
    return ExpandResult(
        field_label=kwargs.get("field_label", "Test"),
        concepts=kwargs.get("concepts", ["ML"]),
        venue_keywords=kwargs.get("venue_keywords", []),
        author_keywords=kwargs.get("author_keywords", []),
        query_terms=kwargs.get("query_terms", []),
        language="en",
    )


# ---------------------------------------------------------------------------
# _cap_candidates
# ---------------------------------------------------------------------------


def test_cap_keeps_all_under_60():
    cands = [_make_candidate(f"src-{i}") for i in range(30)]
    capped = _cap_candidates(cands)
    assert len(capped) == 30


def test_cap_truncates_at_60():
    cands = [_make_candidate(f"src-{i}") for i in range(100)]
    capped = _cap_candidates(cands)
    assert len(capped) == 60


def test_cap_keeps_highest_scores():
    cands = [_make_candidate(f"src-{i}", score=float(79 - i)) for i in range(80)]
    capped = _cap_candidates(cands)
    assert len(capped) == 60
    assert capped[0].relevance_score == 79.0
    assert capped[-1].relevance_score == 20.0


# ---------------------------------------------------------------------------
# _rank_and_group
# ---------------------------------------------------------------------------


def test_rank_groups_by_label():
    items = [
        _make_candidate("Src1", label="", score=5.0),
        _make_candidate("Venue1", label="journal", score=3.0),
        _make_candidate("Venue2", label="conference", score=2.0),
        _make_candidate("Venue3", label="venue", score=1.0),
        _make_candidate("Author1", label="author", score=4.0),
    ]
    pack = _rank_and_group(items)
    assert len(pack.sources) == 1
    assert len(pack.venues) == 3
    assert len(pack.authors) == 1
    assert pack.sources[0].name == "Src1"
    assert pack.authors[0].name == "Author1"


def test_rank_sorts_by_score_descending():
    items = [
        _make_candidate("Low", score=1.0),
        _make_candidate("High", score=10.0),
        _make_candidate("Mid", score=5.0),
    ]
    pack = _rank_and_group(items)
    assert [s.name for s in pack.sources] == ["High", "Mid", "Low"]


# ---------------------------------------------------------------------------
# resolve_verify_rank — full pipeline
# ---------------------------------------------------------------------------


@patch("services.source_discovery._resolve_all", new_callable=AsyncMock)
@patch("services.source_discovery._verify_all", new_callable=AsyncMock)
def test_pipeline_returns_discovery_pack(mock_verify, mock_resolve):
    cache_clear()
    mock_resolve.return_value = [
        _make_candidate("Source A", label="", score=5.0, provenance_url="https://example.com/a"),
        _make_candidate("A Journal", label="journal", score=3.0, provenance_url="https://example.com/j"),
        _make_candidate("Dr. X", label="author", score=4.0, provenance_url="https://example.com/x"),
    ]
    mock_verify.return_value = [
        DiscoveryCandidate(name="Source A", provider="openalex", relevance_score=5.0, verified=True, provenance_url="https://example.com/a"),
        DiscoveryCandidate(name="A Journal", provider="openalex", relevance_score=3.0, label="journal", verified=True, provenance_url="https://example.com/j"),
        DiscoveryCandidate(name="Dr. X", provider="openalex", relevance_score=4.0, label="author", verified=True, provenance_url="https://example.com/x"),
    ]

    result = run_pipeline(_make_result())
    assert isinstance(result, DiscoveryPack)
    assert len(result.sources) == 1
    assert len(result.venues) == 1
    assert len(result.authors) == 1


@patch("services.source_discovery._resolve_all", new_callable=AsyncMock)
@patch("services.source_discovery._verify_all", new_callable=AsyncMock)
def test_pipeline_excludes_unverified(mock_verify, mock_resolve):
    cache_clear()
    mock_resolve.return_value = [
        _make_candidate("Good", label="", score=5.0, provenance_url="https://example.com/good"),
        _make_candidate("Bad", label="", score=3.0, provenance_url="https://example.com/bad"),
    ]
    mock_verify.return_value = [
        DiscoveryCandidate(name="Good", provider="openalex", relevance_score=5.0, verified=True, provenance_url="https://example.com/good"),
        DiscoveryCandidate(name="Bad", provider="openalex", relevance_score=3.0, verified=False, provenance_url="https://example.com/bad"),
    ]

    result = run_pipeline(_make_result())
    assert len(result.sources) == 2  # both retained, but Bad flagged unverified


@patch("services.source_discovery._resolve_all", new_callable=AsyncMock)
@patch("services.source_discovery._verify_all", new_callable=AsyncMock)
def test_pipeline_includes_unverifiable(mock_verify, mock_resolve):
    cache_clear()
    mock_resolve.return_value = [
        _make_candidate("Slow", label="", score=5.0, provenance_url="https://example.com/slow"),
    ]
    mock_verify.return_value = [
        DiscoveryCandidate(name="Slow", provider="openalex", relevance_score=5.0, verified=False, unverifiable=True, provenance_url="https://example.com/slow"),
    ]

    result = run_pipeline(_make_result())
    assert len(result.sources) == 1
    assert result.sources[0].unverifiable is True


@patch("services.source_discovery._resolve_all", new_callable=AsyncMock)
@patch("services.source_discovery._verify_all", new_callable=AsyncMock)
def test_pipeline_empty_on_no_results(mock_verify, mock_resolve):
    cache_clear()
    mock_resolve.return_value = []
    result = run_pipeline(_make_result())
    assert len(result.sources) == 0
    assert len(result.venues) == 0
    assert len(result.authors) == 0


@patch("services.source_discovery._resolve_all", new_callable=AsyncMock)
def test_pipeline_handles_verify_all_exception(mock_resolve):
    cache_clear()
    mock_resolve.return_value = [_make_candidate("A", label="", score=5.0)]
    # Simulate _verify_all raising — should still return empty pack
    with patch("services.source_discovery._verify_all", new_callable=AsyncMock) as mv:
        mv.side_effect = RuntimeError("verify crash")
        result = run_pipeline(_make_result())
    assert isinstance(result, DiscoveryPack)
    assert len(result.sources) == 0


# ---------------------------------------------------------------------------
# _verify_one — HTTP check
# ---------------------------------------------------------------------------


@patch("net_guard.check_url", return_value=None)
@patch("services.source_discovery.httpx.AsyncClient")
def test_verify_one_verified_on_2xx(mock_client_cls, mock_check_url):
    from services.source_discovery import _verify_one
    mock_client = MagicMock()
    mock_client_cls.return_value.__aenter__.return_value = mock_client
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_client.head = AsyncMock(return_value=mock_resp)

    cand = _make_candidate("Test", provenance_url="https://example.com")
    result = run_async(_verify_one(cand))
    assert result.verified is True
    assert result.unverifiable is False


@patch("net_guard.check_url", return_value=None)
@patch("services.source_discovery.httpx.AsyncClient")
def test_verify_one_failed_on_4xx(mock_client_cls, mock_check_url):
    from services.source_discovery import _verify_one
    mock_client = MagicMock()
    mock_client_cls.return_value.__aenter__.return_value = mock_client
    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_client.head = AsyncMock(return_value=mock_resp)

    cand = _make_candidate("Test", provenance_url="https://example.com")
    result = run_async(_verify_one(cand))
    assert result.verified is False


@patch("net_guard.check_url", return_value=None)
@patch("services.source_discovery.httpx.AsyncClient")
def test_verify_one_unverifiable_on_timeout(mock_client_cls, mock_check_url):
    from services.source_discovery import _verify_one
    import httpx
    mock_client = MagicMock()
    mock_client_cls.return_value.__aenter__.return_value = mock_client
    mock_client.head = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    cand = _make_candidate("Test", provenance_url="https://example.com")
    result = run_async(_verify_one(cand))
    assert result.verified is False
    assert result.unverifiable is True


def test_verify_one_unverifiable_no_url():
    from services.source_discovery import _verify_one
    cand = _make_candidate("Test")
    result = run_async(_verify_one(cand))
    assert result.unverifiable is True
    assert result.verified is False


# ---------------------------------------------------------------------------
# _resolve_all — provider orchestration
# ---------------------------------------------------------------------------


def test_resolve_all_calls_providers_with_keywords():
    """Verify that providers are called and results are aggregated."""
    from services.source_discovery import _resolve_all

    mock_provider = MagicMock()
    mock_provider.resolve = AsyncMock(return_value=[])

    class MockProviderClass:
        def __new__(cls):
            return mock_provider

    fake_registry = {"openalex": MockProviderClass}

    expand = _make_result(concepts=["deep learning", "transformers"])

    with patch.dict("providers.PROVIDER_REGISTRY", fake_registry, clear=True):
        results = run_async(_resolve_all(expand))

    assert mock_provider.resolve.await_count == 2  # 2 concepts
    assert results == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_pipeline(expand: ExpandResult) -> DiscoveryPack:
    import asyncio
    return asyncio.run(resolve_verify_rank(expand))


def run_async(coro):
    import asyncio
    return asyncio.run(coro)


def run_tests():
    tests = [
        ("cap_keeps_all_under_60", test_cap_keeps_all_under_60),
        ("cap_truncates_at_60", test_cap_truncates_at_60),
        ("cap_keeps_highest_scores", test_cap_keeps_highest_scores),
        ("rank_groups_by_label", test_rank_groups_by_label),
        ("rank_sorts_by_score_descending", test_rank_sorts_by_score_descending),
        ("pipeline_returns_discovery_pack", test_pipeline_returns_discovery_pack),
        ("pipeline_excludes_unverified", test_pipeline_excludes_unverified),
        ("pipeline_includes_unverifiable", test_pipeline_includes_unverifiable),
        ("pipeline_empty_on_no_results", test_pipeline_empty_on_no_results),
        ("pipeline_handles_verify_all_exception", test_pipeline_handles_verify_all_exception),
        ("verify_one_verified_on_2xx", test_verify_one_verified_on_2xx),
        ("verify_one_failed_on_4xx", test_verify_one_failed_on_4xx),
        ("verify_one_unverifiable_on_timeout", test_verify_one_unverifiable_on_timeout),
        ("verify_one_unverifiable_no_url", test_verify_one_unverifiable_no_url),
        ("resolve_all_calls_providers_with_keywords", test_resolve_all_calls_providers_with_keywords),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅  {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌  {name}: {e}")
            failed += 1
    print(f"\n{'='*40}")
    print(f"  {passed}/{passed + failed} passed")
    if failed:
        print(f"  ❌  {failed} FAILED")
    else:
        print(f"  ✅  ALL PASSED")


if __name__ == "__main__":
    run_tests()
