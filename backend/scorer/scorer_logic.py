"""Pure scoring logic — no network, no framework dependencies.

Extracted here so unit tests can import without needing httpx/fastapi/pydantic.
scorer.py imports from this module.
"""

import json
from typing import Optional

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
