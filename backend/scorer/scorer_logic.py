"""Pure scoring logic — no network, no framework dependencies.

Extracted here so unit tests can import without needing httpx/fastapi/pydantic.
scorer.py imports from this module.
"""

import json
from typing import Any, Optional

_VALID_CONTRIBUTION_TYPES = {
    "method", "benchmark", "survey", "empirical", "theory",
    "position", "tool", "incident", "tutorial", "news", "other",
}
_VALID_RE_DOC_TYPES = {"elicitation", "extraction", "method", "none"}


def clamp_float(val) -> Optional[float]:
    """Clamp a value to [0.0, 1.0], returning None if not convertible."""
    if val is None:
        return None
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return None


def compute_content_cap(scorer_max_chars: int, paper_meta_json: Optional[str]) -> int:
    """Return the effective content cap in characters.

    Doubles the cap (bounded at 12 000) when paper_meta_json indicates
    is_paper=True. Falls back to scorer_max_chars on any parse error.
    """
    cap = scorer_max_chars
    if paper_meta_json:
        try:
            pm = json.loads(paper_meta_json)
            if pm.get("is_paper"):
                cap = min(scorer_max_chars * 2, 12000)
        except (json.JSONDecodeError, TypeError):
            pass
    return cap


def extract_facets(data: Any, facet_schema: Optional[dict]) -> Optional[str]:
    """Story 10.4 — extract per-dimension facet values from an LLM response dict.

    Returns a JSON string like '{"contribution_type": "method", ...}' keyed by the
    schema's dimension IDs, or None if `facet_schema` is missing/empty, no dimension
    keys are present in `data`, or any error occurs (NFR-DA9 — graceful degradation).

    Values are stored verbatim from the LLM — no validation against the dimension's
    `values` list. UX-level validation is deferred to future stories.

    The CS-equivalent schema (dimensions `contribution_type` + `re_document_type`)
    is handled by the generic lookup path: the LLM already emits those keys, so
    they are mirrored into facets_json automatically without special-casing
    (preserves NFR-DA1 for user_id=1).
    """
    try:
        if not facet_schema or not isinstance(data, dict):
            return None
        dimensions = facet_schema.get("dimensions") or []
        if not dimensions:
            return None
        result: dict = {}
        for dim in dimensions:
            if not isinstance(dim, dict):
                continue
            dim_id = dim.get("id")
            if dim_id and dim_id in data:
                result[dim_id] = data[dim_id]
        return json.dumps(result) if result else None
    except Exception:
        return None
