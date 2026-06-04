"""Tests for Story 10.4 — scorer emits facets_json keyed by user's facet schema.

Verifies:
- `extract_facets()` returns serialized JSON keyed by dimension IDs from LLM data
- CS-equivalent schema → mirrors `contribution_type` + `re_document_type` values
- Returns None when schema is absent / empty / malformed (NFR-DA9)
- `validate_score_result()` integrates facets extraction; default param keeps
  byte-identical legacy behavior
- `ScoreResult.facets_json` is None when LLM omits matching dimension keys

The `scorer_logic.extract_facets` tests are hermetic (no Docker required).
The `validate_score_result` integration tests require the scorer image.

Run inside Docker:
    docker-compose exec api python -m pytest \\
        backend/scorer/tests/test_scorer_facets_emission.py -v
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCORER_DIR = Path(__file__).parent.parent

if str(SCORER_DIR) not in sys.path:
    sys.path.insert(0, str(SCORER_DIR))

# Pure logic — always importable
from scorer_logic import extract_facets


def _cs_schema() -> dict:
    return {
        "version": 1,
        "dimensions": [
            {
                "id": "contribution_type",
                "label": "Contribution Type",
                "type": "enum",
                "values": [
                    "method", "benchmark", "survey", "empirical",
                    "theory", "position", "tool", "incident",
                    "tutorial", "news", "other",
                ],
            },
            {
                "id": "re_document_type",
                "label": "RE Document Type",
                "type": "enum",
                "values": ["elicitation", "extraction", "method", "none"],
            },
        ],
    }


def _custom_schema() -> dict:
    return {
        "version": 1,
        "dimensions": [
            {
                "id": "study_phase",
                "label": "Study Phase",
                "type": "enum",
                "values": ["pilot", "field", "lab", "review"],
            },
            {
                "id": "methodology",
                "label": "Methodology",
                "type": "enum",
                "values": ["case-study", "experiment", "survey"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# extract_facets — pure logic, hermetic
# ---------------------------------------------------------------------------

class TestExtractFacetsCustomSchema:
    """AC 1: extract values matching the schema's dimension IDs from LLM data."""

    def test_returns_json_string(self):
        data = {"study_phase": "pilot", "methodology": "experiment", "score": 7}
        result = extract_facets(data, _custom_schema())
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed == {"study_phase": "pilot", "methodology": "experiment"}

    def test_ignores_unrelated_keys(self):
        data = {
            "study_phase": "field",
            "tags": ["a", "b"],
            "novelty": 0.8,
            "extra_key": "ignored",
        }
        result = extract_facets(data, _custom_schema())
        parsed = json.loads(result)
        assert "tags" not in parsed
        assert "extra_key" not in parsed
        assert parsed == {"study_phase": "field"}

    def test_extracts_partial_when_some_dims_missing(self):
        data = {"study_phase": "lab"}  # methodology key absent
        result = extract_facets(data, _custom_schema())
        parsed = json.loads(result)
        assert parsed == {"study_phase": "lab"}


class TestExtractFacetsCSEquivalent:
    """AC 2: CS-equivalent schema mirrors contribution_type + re_document_type."""

    def test_mirrors_cs_fields(self):
        data = {
            "score": 8.5,
            "contribution_type": "method",
            "re_document_type": "elicitation",
            "tags": ["x"],
        }
        result = extract_facets(data, _cs_schema())
        parsed = json.loads(result)
        assert parsed == {
            "contribution_type": "method",
            "re_document_type": "elicitation",
        }

    def test_mirrors_none_re_document(self):
        data = {
            "contribution_type": "survey",
            "re_document_type": "none",
        }
        result = extract_facets(data, _cs_schema())
        parsed = json.loads(result)
        assert parsed["contribution_type"] == "survey"
        assert parsed["re_document_type"] == "none"


class TestExtractFacetsAbsentOrEmpty:
    """AC 1, 4: missing/empty schema or no matching keys → None."""

    def test_none_schema_returns_none(self):
        assert extract_facets({"contribution_type": "method"}, None) is None

    def test_empty_dict_schema_returns_none(self):
        assert extract_facets({"contribution_type": "method"}, {}) is None

    def test_empty_dimensions_returns_none(self):
        schema = {"version": 1, "dimensions": []}
        assert extract_facets({"contribution_type": "method"}, schema) is None

    def test_no_matching_keys_returns_none(self):
        data = {"score": 5.0, "tags": []}  # no facet keys at all
        assert extract_facets(data, _custom_schema()) is None


class TestExtractFacetsGracefulDegradation:
    """AC 4: any error path returns None instead of raising (NFR-DA9)."""

    def test_non_dict_data_returns_none(self):
        assert extract_facets("not a dict", _custom_schema()) is None
        assert extract_facets(None, _custom_schema()) is None
        assert extract_facets([{"study_phase": "pilot"}], _custom_schema()) is None

    def test_malformed_dimension_entries_skipped(self):
        schema = {
            "version": 1,
            "dimensions": [
                "not_a_dict",
                {"id": "valid_dim", "label": "Valid", "type": "enum", "values": ["a"]},
                None,
            ],
        }
        data = {"valid_dim": "a", "other": "ignored"}
        result = extract_facets(data, schema)
        assert json.loads(result) == {"valid_dim": "a"}

    def test_dimension_without_id_is_skipped(self):
        schema = {
            "version": 1,
            "dimensions": [
                {"label": "No ID", "type": "enum", "values": ["a"]},
                {"id": "with_id", "label": "OK", "type": "enum", "values": ["x"]},
            ],
        }
        data = {"with_id": "x"}
        result = extract_facets(data, schema)
        assert json.loads(result) == {"with_id": "x"}


# ---------------------------------------------------------------------------
# validate_score_result integration — requires httpx/pydantic (Docker)
# ---------------------------------------------------------------------------

def _check_scorer_deps() -> bool:
    try:
        import httpx  # noqa: F401
        import pydantic  # noqa: F401
        return True
    except ImportError:
        return False


SCORER_DEPS_AVAILABLE = _check_scorer_deps()

SKIP_SCORER = pytest.mark.skipif(
    not SCORER_DEPS_AVAILABLE,
    reason=(
        "Scorer deps (httpx/pydantic) not available — run inside Docker: "
        "docker-compose exec api python -m pytest "
        "backend/scorer/tests/test_scorer_facets_emission.py -v"
    ),
)


@SKIP_SCORER
class TestValidateScoreResultIntegration:
    """AC 1, 2, 3: validate_score_result wires facets_json without breaking legacy."""

    def test_facets_json_none_when_schema_absent(self):
        # AC 3 (no regression): default param keeps facets_json None
        os.environ.setdefault("OLLAMA_URL", "http://stub")
        from scorer import validate_score_result
        data = {
            "score": 8.0,
            "contribution_type": "method",
            "re_document_type": "none",
        }
        result = validate_score_result(data)
        assert result.facets_json is None
        # Legacy fields still extracted
        assert result.score == 8.0
        assert result.contribution_type == "method"
        assert result.re_document_type == "none"

    def test_facets_json_populated_with_cs_schema(self):
        # AC 2: CS-equivalent schema mirrors legacy fields into facets_json
        os.environ.setdefault("OLLAMA_URL", "http://stub")
        from scorer import validate_score_result
        data = {
            "score": 7.0,
            "contribution_type": "survey",
            "re_document_type": "extraction",
        }
        result = validate_score_result(data, _cs_schema())
        assert result.facets_json is not None
        assert json.loads(result.facets_json) == {
            "contribution_type": "survey",
            "re_document_type": "extraction",
        }
        # Legacy fields still populated for user_id=1 (NFR-DA1)
        assert result.contribution_type == "survey"
        assert result.re_document_type == "extraction"

    def test_facets_json_populated_with_custom_schema(self):
        # AC 1: custom schema picks up custom dimension keys
        os.environ.setdefault("OLLAMA_URL", "http://stub")
        from scorer import validate_score_result
        data = {
            "score": 6.5,
            "study_phase": "field",
            "methodology": "case-study",
            "contribution_type": "method",
        }
        result = validate_score_result(data, _custom_schema())
        parsed = json.loads(result.facets_json)
        assert parsed == {"study_phase": "field", "methodology": "case-study"}
        # contribution_type still extracted into the legacy column (not in schema)
        assert result.contribution_type == "method"

    def test_facets_json_none_when_llm_omits_dim_keys(self):
        # AC 4: partial data still persisted; facets_json is None
        os.environ.setdefault("OLLAMA_URL", "http://stub")
        from scorer import validate_score_result
        data = {
            "score": 5.0,
            "tags": ["abc"],  # no dimension keys at all
        }
        result = validate_score_result(data, _custom_schema())
        assert result.facets_json is None
        # Partial score still extracted
        assert result.score == 5.0

    def test_score_result_facets_json_field_defaults_none(self):
        # AC 3: backward-compat — ScoreResult constructable without facets_json
        os.environ.setdefault("OLLAMA_URL", "http://stub")
        from scorer import ScoreResult
        sr = ScoreResult(score=5.0)
        assert sr.facets_json is None
