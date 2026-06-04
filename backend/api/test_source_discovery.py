"""Tests for source_discovery.py (Story 13-1 — Discovery EXPAND)."""

import json
import os
import sys
from unittest.mock import AsyncMock, patch

_api_dir = os.path.join(os.path.dirname(__file__))
for p in [_api_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from services.source_discovery import (
    ExpandResult,
    _degraded_result,
    _extract_json_object,
    _has_url_or_doi,
    cache_clear,
    expand,
)

SAMPLE_RESPONSE = {
    "field_label": "Computational Linguistics",
    "concepts": ["syntax parsing", "semantic role labeling", "dependency parsing"],
    "venue_keywords": ["ACL", "EMNLP", "NAACL", "Computational Linguistics"],
    "author_keywords": ["Jurafsky", "Manning", "Goldberg"],
    "query_terms": ["syntax parsing transformer", "semantic role labeling BERT"],
    "language": "en",
}


# ---------------------------------------------------------------------------
# _has_url_or_doi
# ---------------------------------------------------------------------------


def test_url_detected():
    assert _has_url_or_doi("https://example.com")
    assert _has_url_or_doi("http://arxiv.org/abs/2301.00001")
    assert _has_url_or_doi("see https://openreview.net for details")


def test_doi_detected():
    assert _has_url_or_doi("10.1234/5678")
    assert _has_url_or_doi("doi.org/10.1234/5678")
    assert _has_url_or_doi("ref: 10.1000/xyz123")


def test_clean_text_not_detected():
    assert not _has_url_or_doi("syntax parsing")
    assert not _has_url_or_doi("ACL")
    assert not _has_url_or_doi("Jurafsky")
    assert not _has_url_or_doi("10" * 100)  # no dot after 10


# ---------------------------------------------------------------------------
# ExpandResult validator — URL/DOI stripping
# ---------------------------------------------------------------------------


def test_expand_result_validator_strips_urls():
    dirty = {
        "field_label": "ML",
        "concepts": ["deep learning", "https://arxiv.org/abs/2301.00001", "transformers"],
        "venue_keywords": ["NeurIPS", "10.1234/5678"],
        "author_keywords": [],
        "query_terms": [],
        "language": "en",
    }
    result = ExpandResult.model_validate(dirty)
    assert result.concepts == ["deep learning", "transformers"]
    assert result.venue_keywords == ["NeurIPS"]


def test_expand_result_validator_clean():
    result = ExpandResult.model_validate(SAMPLE_RESPONSE)
    assert result.field_label == "Computational Linguistics"
    assert len(result.concepts) == 3
    assert result.language == "en"
    assert result.degraded is False


def test_expand_result_defaults():
    result = ExpandResult()
    assert result.field_label == ""
    assert result.concepts == []
    assert result.degraded is False


# ---------------------------------------------------------------------------
# _extract_json_object
# ---------------------------------------------------------------------------


def test_extract_plain_json():
    obj = _extract_json_object('{"a": 1}')
    assert obj == {"a": 1}


def test_extract_fenced_json():
    obj = _extract_json_object("some preamble\n```json\n{\"a\": 1}\n```\ntrailing")
    assert obj == {"a": 1}


def test_extract_balanced_brace():
    obj = _extract_json_object("text { \"a\": 1, \"b\": [1,2,3] } more")
    assert obj == {"a": 1, "b": [1, 2, 3]}


def test_extract_returns_none_on_empty():
    assert _extract_json_object("") is None


# ---------------------------------------------------------------------------
# expand() — clean LLM path
# ---------------------------------------------------------------------------


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_returns_valid_result(mock_call_llm):
    cache_clear()
    mock_call_llm.return_value = json.dumps(SAMPLE_RESPONSE)
    result = run_expand("urban mobility policy")
    assert result.field_label == "Computational Linguistics"
    assert result.concepts == ["syntax parsing", "semantic role labeling", "dependency parsing"]
    assert result.language == "en"
    assert result.degraded is False
    mock_call_llm.assert_awaited_once()


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_cache_prevents_second_llm_call(mock_call_llm):
    cache_clear()
    mock_call_llm.return_value = json.dumps(SAMPLE_RESPONSE)

    r1 = run_expand("urban mobility policy")
    assert r1.field_label == "Computational Linguistics"
    assert mock_call_llm.await_count == 1

    r2 = run_expand("urban mobility policy")
    assert r2.field_label == "Computational Linguistics"
    assert mock_call_llm.await_count == 1, "LLM should not be called again (cache hit)"


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_cache_misses_for_different_text(mock_call_llm):
    cache_clear()
    mock_call_llm.return_value = json.dumps(SAMPLE_RESPONSE)

    run_expand("urban mobility policy")
    assert mock_call_llm.await_count == 1

    mock_call_llm.return_value = json.dumps({**SAMPLE_RESPONSE, "field_label": "Urban Planning"})
    r2 = run_expand("autonomous driving")
    assert r2.field_label == "Urban Planning"
    assert mock_call_llm.await_count == 2, "LLM should be called again for different input"


# ---------------------------------------------------------------------------
# Degraded mode
# ---------------------------------------------------------------------------


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_degraded_on_llm_none(mock_call_llm):
    cache_clear()
    mock_call_llm.return_value = None
    result = run_expand("some thesis text")
    assert result.degraded is True
    assert result.field_label == "some thesis text"[:40]


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_degraded_on_bad_json(mock_call_llm):
    cache_clear()
    mock_call_llm.return_value = "this is not json"
    result = run_expand("some thesis")
    assert result.degraded is True


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_degraded_on_exception(mock_call_llm):
    cache_clear()
    mock_call_llm.side_effect = RuntimeError("LLM down")
    result = run_expand("some thesis")
    assert result.degraded is True
    assert result.field_label == "some thesis"[:40]


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_degraded_never_cached(mock_call_llm):
    cache_clear()
    mock_call_llm.side_effect = RuntimeError("LLM down")
    r1 = run_expand("test text")
    assert r1.degraded is True
    assert mock_call_llm.await_count == 1

    mock_call_llm.side_effect = None
    mock_call_llm.return_value = json.dumps(SAMPLE_RESPONSE)
    r2 = run_expand("test text")
    assert r2.degraded is False
    assert r2.field_label == "Computational Linguistics"
    assert mock_call_llm.await_count == 2, "Should retry LLM after degraded (not cached)"

# ---------------------------------------------------------------------------
# URL/DOI in LLM response → stripped via validator
# ---------------------------------------------------------------------------


@patch("services.source_discovery._call_llm", new_callable=AsyncMock)
def test_expand_strips_urls_from_llm_output(mock_call_llm):
    cache_clear()
    dirty = {
        "field_label": "CS",
        "concepts": ["ML", "https://arxiv.org/abs/2301.00001", "data mining"],
        "venue_keywords": ["KDD", "10.1234/5678", "ICML"],
        "author_keywords": [],
        "query_terms": [],
        "language": "en",
    }
    mock_call_llm.return_value = json.dumps(dirty)
    result = run_expand("data science")
    assert result.concepts == ["ML", "data mining"]
    assert result.venue_keywords == ["KDD", "ICML"]
    assert result.degraded is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_expand(text: str) -> ExpandResult:
    """Synchronous wrapper around async expand()."""
    import asyncio
    return asyncio.run(expand(text))


def run_tests():
    tests = [
        ("url_detected", test_url_detected),
        ("doi_detected", test_doi_detected),
        ("clean_text_not_detected", test_clean_text_not_detected),
        ("expand_result_validator_strips_urls", test_expand_result_validator_strips_urls),
        ("expand_result_validator_clean", test_expand_result_validator_clean),
        ("expand_result_defaults", test_expand_result_defaults),
        ("extract_plain_json", test_extract_plain_json),
        ("extract_fenced_json", test_extract_fenced_json),
        ("extract_balanced_brace", test_extract_balanced_brace),
        ("extract_returns_none_on_empty", test_extract_returns_none_on_empty),
        ("expand_returns_valid_result", test_expand_returns_valid_result),
        ("expand_cache_prevents_second_llm_call", test_expand_cache_prevents_second_llm_call),
        ("expand_cache_misses_for_different_text", test_expand_cache_misses_for_different_text),
        ("expand_degraded_on_llm_none", test_expand_degraded_on_llm_none),
        ("expand_degraded_on_bad_json", test_expand_degraded_on_bad_json),
        ("expand_degraded_on_exception", test_expand_degraded_on_exception),
        ("expand_degraded_never_cached", test_expand_degraded_never_cached),
        ("expand_strips_urls_from_llm_output", test_expand_strips_urls_from_llm_output),
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
