"""Unit tests for scorer_logic.py — no network calls, no Docker required.

Tests cover:
- validate_score_result: extraction + clamping of all new fields
- compute_content_cap: SCORER_MAX_CHARS + paper-aware auto-raise
- clamp_float helper
"""

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

SCORER_DIR = Path(__file__).parent.parent

if str(SCORER_DIR) not in sys.path:
    sys.path.insert(0, str(SCORER_DIR))

# Import pure logic module — no httpx/fastapi/pydantic required
from scorer_logic import (
    _VALID_CONTRIBUTION_TYPES,
    _VALID_RE_DOC_TYPES,
    clamp_float,
    compute_content_cap,
)

# Import validate_score_result from scorer via a lazy approach that avoids
# triggering httpx/fastapi imports at collection time.
# We define a minimal validate_score_result here that mirrors scorer.py logic,
# keeping tests hermetic.  The scorer integration is covered by the Docker tests.

def validate_score_result(data: dict) -> dict:
    """Mirror of scorer.validate_score_result — pure Python, no deps."""
    score = data.get("score", 5)
    try:
        score = float(score)
        score = max(0.0, min(10.0, score))
    except (TypeError, ValueError):
        score = 5.0

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags[:5]]

    summary_bullets = data.get("summary_bullets", [])
    if not isinstance(summary_bullets, list):
        summary_bullets = []
    summary_bullets = [str(b) for b in summary_bullets[:4]]

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    contribution_type = data.get("contribution_type")
    if contribution_type not in _VALID_CONTRIBUTION_TYPES:
        contribution_type = None

    re_document_type = data.get("re_document_type")
    if re_document_type not in _VALID_RE_DOC_TYPES:
        re_document_type = None

    return {
        "score": score,
        "tags": tags,
        "summary_bullets": summary_bullets,
        "reason": reason,
        "contribution_type": contribution_type,
        "re_document_type": re_document_type,
        "novelty": clamp_float(data.get("novelty")),
        "rigor": clamp_float(data.get("rigor")),
        "relevance_to_topics": clamp_float(data.get("relevance_to_topics")),
    }


# ---------------------------------------------------------------------------
# validate_score_result — baseline fields unchanged
# ---------------------------------------------------------------------------

class TestValidateBaselineFields:
    def _base(self, **overrides):
        data = {
            "score": 7.5,
            "tags": ["kubernetes", "eBPF"],
            "summary_bullets": ["Point A.", "Point B."],
            "reason": "Relevant to infra.",
        }
        data.update(overrides)
        return data

    def test_score_extracted(self):
        r = validate_score_result(self._base())
        assert r["score"] == 7.5

    def test_score_clamped_above_10(self):
        r = validate_score_result(self._base(score=15))
        assert r["score"] == 10.0

    def test_score_clamped_below_0(self):
        r = validate_score_result(self._base(score=-3))
        assert r["score"] == 0.0

    def test_tags_extracted(self):
        r = validate_score_result(self._base())
        assert r["tags"] == ["kubernetes", "eBPF"]

    def test_tags_truncated_to_5(self):
        r = validate_score_result(self._base(tags=["a", "b", "c", "d", "e", "f"]))
        assert len(r["tags"]) == 5

    def test_reason_extracted(self):
        r = validate_score_result(self._base())
        assert r["reason"] == "Relevant to infra."


# ---------------------------------------------------------------------------
# validate_score_result — new research fields
# ---------------------------------------------------------------------------

class TestValidateResearchFields:
    def _full(self, **overrides):
        data = {
            "score": 8.0,
            "tags": ["requirements engineering"],
            "summary_bullets": ["Novel method."],
            "reason": "Strong RE paper.",
            "contribution_type": "method",
            "re_document_type": "elicitation",
            "novelty": 0.85,
            "rigor": 0.9,
            "relevance_to_topics": 0.95,
        }
        data.update(overrides)
        return data

    def test_contribution_type_valid(self):
        r = validate_score_result(self._full())
        assert r["contribution_type"] == "method"

    def test_all_valid_contribution_types_accepted(self):
        for ct in _VALID_CONTRIBUTION_TYPES:
            r = validate_score_result(self._full(contribution_type=ct))
            assert r["contribution_type"] == ct

    def test_invalid_contribution_type_becomes_none(self):
        r = validate_score_result(self._full(contribution_type="invalid_type"))
        assert r["contribution_type"] is None

    def test_null_contribution_type_becomes_none(self):
        r = validate_score_result(self._full(contribution_type=None))
        assert r["contribution_type"] is None

    def test_missing_contribution_type_becomes_none(self):
        data = self._full()
        del data["contribution_type"]
        r = validate_score_result(data)
        assert r["contribution_type"] is None

    def test_re_document_type_valid(self):
        r = validate_score_result(self._full())
        assert r["re_document_type"] == "elicitation"

    def test_all_valid_re_doc_types_accepted(self):
        for rdt in _VALID_RE_DOC_TYPES:
            r = validate_score_result(self._full(re_document_type=rdt))
            assert r["re_document_type"] == rdt

    def test_invalid_re_document_type_becomes_none(self):
        r = validate_score_result(self._full(re_document_type="unknown"))
        assert r["re_document_type"] is None

    def test_novelty_extracted(self):
        r = validate_score_result(self._full())
        assert r["novelty"] == pytest.approx(0.85)

    def test_rigor_extracted(self):
        r = validate_score_result(self._full())
        assert r["rigor"] == pytest.approx(0.9)

    def test_relevance_to_topics_extracted(self):
        r = validate_score_result(self._full())
        assert r["relevance_to_topics"] == pytest.approx(0.95)

    def test_novelty_clamped_above_1(self):
        r = validate_score_result(self._full(novelty=1.5))
        assert r["novelty"] == pytest.approx(1.0)

    def test_novelty_clamped_below_0(self):
        r = validate_score_result(self._full(novelty=-0.2))
        assert r["novelty"] == pytest.approx(0.0)

    def test_novelty_null_becomes_none(self):
        r = validate_score_result(self._full(novelty=None))
        assert r["novelty"] is None

    def test_rigor_null_becomes_none(self):
        r = validate_score_result(self._full(rigor=None))
        assert r["rigor"] is None

    def test_relevance_null_becomes_none(self):
        r = validate_score_result(self._full(relevance_to_topics=None))
        assert r["relevance_to_topics"] is None

    def test_missing_research_fields_all_none(self):
        """When LLM uses infra profile — no research fields in response."""
        data = {
            "score": 7.0,
            "tags": ["linux"],
            "summary_bullets": ["Good post."],
            "reason": "Relevant infra content.",
        }
        r = validate_score_result(data)
        assert r["contribution_type"] is None
        assert r["re_document_type"] is None
        assert r["novelty"] is None
        assert r["rigor"] is None
        assert r["relevance_to_topics"] is None

    def test_string_novelty_coerced_to_float(self):
        r = validate_score_result(self._full(novelty="0.7"))
        assert r["novelty"] == pytest.approx(0.7)

    def test_non_numeric_novelty_becomes_none(self):
        r = validate_score_result(self._full(novelty="high"))
        assert r["novelty"] is None


# ---------------------------------------------------------------------------
# clamp_float helper (from scorer_logic)
# ---------------------------------------------------------------------------

class TestClampFloat:
    def test_within_range(self):
        assert clamp_float(0.5) == pytest.approx(0.5)

    def test_above_1_clamped(self):
        assert clamp_float(2.0) == pytest.approx(1.0)

    def test_below_0_clamped(self):
        assert clamp_float(-1.0) == pytest.approx(0.0)

    def test_none_returns_none(self):
        assert clamp_float(None) is None

    def test_string_coerced(self):
        assert clamp_float("0.8") == pytest.approx(0.8)

    def test_non_numeric_string_returns_none(self):
        assert clamp_float("high") is None


# ---------------------------------------------------------------------------
# compute_content_cap (from scorer_logic)
# ---------------------------------------------------------------------------

class TestComputeContentCap:
    def test_default_cap_applied(self):
        assert compute_content_cap(6000, None) == 6000

    def test_custom_cap_applied(self):
        assert compute_content_cap(100, None) == 100

    def test_paper_doubles_cap(self):
        pm = json.dumps({"is_paper": True})
        assert compute_content_cap(100, pm) == 200

    def test_paper_cap_bounded_at_12000(self):
        pm = json.dumps({"is_paper": True})
        assert compute_content_cap(7000, pm) == 12000

    def test_paper_cap_exactly_at_boundary(self):
        pm = json.dumps({"is_paper": True})
        # 6000 * 2 = 12000 — exactly at the ceiling
        assert compute_content_cap(6000, pm) == 12000

    def test_non_paper_uses_default_cap(self):
        pm = json.dumps({"is_paper": False})
        assert compute_content_cap(100, pm) == 100

    def test_missing_is_paper_key_uses_default_cap(self):
        pm = json.dumps({"source": "arxiv"})
        assert compute_content_cap(100, pm) == 100

    def test_malformed_json_falls_back_to_default(self):
        assert compute_content_cap(100, "{not valid json}") == 100

    def test_none_paper_meta_uses_default_cap(self):
        assert compute_content_cap(100, None) == 100

    def test_empty_string_paper_meta_uses_default_cap(self):
        assert compute_content_cap(100, "") == 100

    def test_content_truncated_to_cap(self):
        cap = compute_content_cap(10, None)
        content = "x" * 50
        preview = content[:cap]
        assert len(preview) == 10

    def test_paper_content_truncated_to_doubled_cap(self):
        pm = json.dumps({"is_paper": True})
        cap = compute_content_cap(10, pm)
        content = "x" * 50
        preview = content[:cap]
        assert len(preview) == 20
