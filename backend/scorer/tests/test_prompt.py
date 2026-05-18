"""Unit tests for backend/scorer/prompt.py file-loader logic.

These tests exercise the module's behavior by importing it with different
PROMPT_PROFILE env-var values. Because prompt.py runs at import time, each
test re-imports the module inside a clean environment using importlib.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

# Locate the scorer package directory so we can force-reimport prompt.py
SCORER_DIR = Path(__file__).parent.parent


def _reload_prompt(profile: str):
    """Set PROMPT_PROFILE, remove any cached import, and reimport prompt."""
    os.environ["PROMPT_PROFILE"] = profile
    sys.modules.pop("prompt", None)
    # Ensure scorer dir is on path
    if str(SCORER_DIR) not in sys.path:
        sys.path.insert(0, str(SCORER_DIR))
    return importlib.import_module("prompt")


def teardown_function():
    """Clean up env var and module cache after each test."""
    os.environ.pop("PROMPT_PROFILE", None)
    sys.modules.pop("prompt", None)


# ---------------------------------------------------------------------------
# AC 1 — loader exposes SYSTEM_PROMPT as a non-empty string
# ---------------------------------------------------------------------------

class TestLoaderExposesSystemPrompt:
    def test_infra_profile_loads_string(self):
        mod = _reload_prompt("infra")
        assert isinstance(mod.SYSTEM_PROMPT, str)
        assert len(mod.SYSTEM_PROMPT) > 100

    def test_research_profile_loads_string(self):
        mod = _reload_prompt("research")
        assert isinstance(mod.SYSTEM_PROMPT, str)
        assert len(mod.SYSTEM_PROMPT) > 100

    def test_unified_profile_loads_string(self):
        mod = _reload_prompt("unified")
        assert isinstance(mod.SYSTEM_PROMPT, str)
        assert len(mod.SYSTEM_PROMPT) > 100


# ---------------------------------------------------------------------------
# AC 4 — infra.md is character-perfect copy of the original hard-coded prompt
# ---------------------------------------------------------------------------

class TestInfraProfileContent:
    EXPECTED_OPENING = (
        "You are a technical content curation assistant for Arona, "
        "a Cloud & Systems engineer"
    )
    EXPECTED_SECTIONS = [
        "## READER PROFILE",
        "## SCORING RUBRIC",
        "## PRIORITY THEMES",
        "## RESPONSE FORMAT",
    ]
    EXPECTED_JSON_FIELDS = ['"score"', '"tags"', '"summary_bullets"', '"reason"']
    EXPECTED_RUBRIC_LEVELS = ["9-10", "7-8", "5-6", "3-4", "0-2"]

    def test_infra_starts_with_original_opening(self):
        mod = _reload_prompt("infra")
        assert mod.SYSTEM_PROMPT.startswith(self.EXPECTED_OPENING)

    def test_infra_contains_all_sections(self):
        mod = _reload_prompt("infra")
        for section in self.EXPECTED_SECTIONS:
            assert section in mod.SYSTEM_PROMPT, f"Missing section: {section}"

    def test_infra_contains_all_json_fields(self):
        mod = _reload_prompt("infra")
        for field in self.EXPECTED_JSON_FIELDS:
            assert field in mod.SYSTEM_PROMPT, f"Missing JSON field: {field}"

    def test_infra_contains_all_rubric_levels(self):
        mod = _reload_prompt("infra")
        for level in self.EXPECTED_RUBRIC_LEVELS:
            assert level in mod.SYSTEM_PROMPT, f"Missing rubric level: {level}"

    def test_infra_no_leading_whitespace(self):
        """Original SYSTEM_PROMPT had no leading newline — infra.md must match."""
        mod = _reload_prompt("infra")
        assert not mod.SYSTEM_PROMPT.startswith("\n")
        assert not mod.SYSTEM_PROMPT.startswith(" ")


# ---------------------------------------------------------------------------
# AC 2 — research.md contains expected research-specific content
# ---------------------------------------------------------------------------

class TestResearchProfileContent:
    def test_research_mentions_requirements_engineering(self):
        mod = _reload_prompt("research")
        assert "Requirements Engineering" in mod.SYSTEM_PROMPT or \
               "requirements engineering" in mod.SYSTEM_PROMPT.lower()

    def test_research_mentions_mbse(self):
        mod = _reload_prompt("research")
        assert "MBSE" in mod.SYSTEM_PROMPT or "Model-Based" in mod.SYSTEM_PROMPT

    def test_research_contains_json_response_format(self):
        mod = _reload_prompt("research")
        assert '"score"' in mod.SYSTEM_PROMPT
        assert '"tags"' in mod.SYSTEM_PROMPT

    def test_research_contains_rubric(self):
        mod = _reload_prompt("research")
        assert "9-10" in mod.SYSTEM_PROMPT
        assert "0-2" in mod.SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# AC 2 — unified.md contains content from both modes
# ---------------------------------------------------------------------------

class TestUnifiedProfileContent:
    def test_unified_mentions_infra_topics(self):
        mod = _reload_prompt("unified")
        assert "Kubernetes" in mod.SYSTEM_PROMPT

    def test_unified_mentions_research_topics(self):
        mod = _reload_prompt("unified")
        assert "Requirements Engineering" in mod.SYSTEM_PROMPT or \
               "ARISE" in mod.SYSTEM_PROMPT

    def test_unified_has_contribution_type_field(self):
        """unified.md extends the JSON schema with contribution_type."""
        mod = _reload_prompt("unified")
        assert "contribution_type" in mod.SYSTEM_PROMPT

    def test_unified_contains_rubric(self):
        mod = _reload_prompt("unified")
        assert "9-10" in mod.SYSTEM_PROMPT
        assert "0-2" in mod.SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# AC 3 — SYSTEM_PROMPT name is preserved (backward compat with scorer.py)
# ---------------------------------------------------------------------------

class TestSystemPromptNamePreserved:
    def test_attribute_name_is_system_prompt(self):
        mod = _reload_prompt("unified")
        assert hasattr(mod, "SYSTEM_PROMPT")

    def test_system_prompt_is_string_not_none(self):
        mod = _reload_prompt("unified")
        assert mod.SYSTEM_PROMPT is not None


# ---------------------------------------------------------------------------
# AC 5 — invalid profile raises FileNotFoundError at import time
# ---------------------------------------------------------------------------

class TestInvalidProfileFails:
    def test_unknown_profile_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            _reload_prompt("does_not_exist")
        assert "does_not_exist" in str(exc_info.value)

    def test_error_message_names_the_bad_profile(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            _reload_prompt("typo_profile")
        assert "typo_profile" in str(exc_info.value)

    def test_error_message_lists_valid_profiles(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            _reload_prompt("nonexistent")
        error_msg = str(exc_info.value)
        # Error should mention at least one of the valid profiles
        assert any(p in error_msg for p in ["infra", "research", "unified"])

    def test_empty_string_profile_raises_file_not_found(self):
        """Empty string is not a valid profile name."""
        with pytest.raises(FileNotFoundError):
            _reload_prompt("")


# ---------------------------------------------------------------------------
# AC 1 — default profile is "unified" when env var is absent
# ---------------------------------------------------------------------------

class TestDefaultProfile:
    def test_missing_env_var_defaults_to_unified(self):
        os.environ.pop("PROMPT_PROFILE", None)
        sys.modules.pop("prompt", None)
        if str(SCORER_DIR) not in sys.path:
            sys.path.insert(0, str(SCORER_DIR))
        mod = importlib.import_module("prompt")
        # unified.md contains contribution_type — use as a fingerprint
        assert "contribution_type" in mod.SYSTEM_PROMPT
