"""Tests for PromptBuilder (Story 5.1, FR-MT-26)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scorer package is importable
_SCORER_DIR = Path(__file__).resolve().parent.parent
if str(_SCORER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCORER_DIR))

from prompt_builder import (
    PromptBuilder,
    UserScoringContext,
    sanitize,
)


class TestSanitize:
    def test_strips_control_chars(self):
        assert sanitize("hello\x00world") == "helloworld"

    def test_strips_newlines(self):
        assert sanitize("line1\nline2") == "line1 line2"

    def test_trims_whitespace(self):
        assert sanitize("  hello  ") == "hello"

    def test_handles_empty(self):
        assert sanitize("") == ""

    def test_handles_none(self):
        assert sanitize(None) == ""

    def test_preserves_normal_text(self):
        assert sanitize("Hello, World!") == "Hello, World!"


class TestPromptBuilder:
    def test_build_returns_string(self):
        ctx = UserScoringContext()
        result = PromptBuilder.build(ctx)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_build_injects_thesis_title(self):
        ctx = UserScoringContext(thesis_title="My Custom Thesis")
        result = PromptBuilder.build(ctx)
        assert '"My Custom Thesis"' in result

    def test_build_injects_thesis_question(self):
        ctx = UserScoringContext(thesis_question="What is the meaning?")
        result = PromptBuilder.build(ctx)
        assert "What is the meaning?" in result

    def test_build_injects_tracked_venues(self):
        ctx = UserScoringContext(tracked_venues=["VenueA", "VenueB"])
        result = PromptBuilder.build(ctx)
        assert "VenueA, VenueB" in result

    def test_build_injects_clusters(self):
        ctx = UserScoringContext(
            scoring_clusters=[
                {"id": "Z", "name": "Custom Cluster", "description": "A custom cluster description.", "reward_level": "critical"},
            ]
        )
        result = PromptBuilder.build(ctx)
        assert "Cluster Z" in result
        assert "Custom Cluster" in result
        assert "Critical reward" in result
        assert "A custom cluster description." in result

    def test_build_multiple_clusters(self):
        ctx = UserScoringContext(
            scoring_clusters=[
                {"id": "X", "name": "Alpha", "description": "Desc X.", "reward_level": "high"},
                {"id": "Y", "name": "Beta", "description": "Desc Y.", "reward_level": "critical"},
            ]
        )
        result = PromptBuilder.build(ctx)
        assert "Cluster X" in result
        assert "Cluster Y" in result
        assert "Alpha" in result
        assert "Beta" in result

    def test_default_profile_loads_unified(self):
        ctx = UserScoringContext()
        result = PromptBuilder.build(ctx)
        assert "DUAL-MODE SCORING" in result  # unified.md specific

    def test_research_profile(self):
        ctx = UserScoringContext(prompt_profile="research")
        result = PromptBuilder.build(ctx)
        assert "RESEARCH PROFILE" in result
        assert "SCORING RUBRIC" in result

    def test_infra_profile_unchanged(self):
        ctx = UserScoringContext(prompt_profile="infra")
        result = PromptBuilder.build(ctx)
        assert "PRIORITY THEMES" in result  # infra.md specific
        # infra has no profile section to replace (uses ## READER PROFILE instead)
        assert "## READER PROFILE" in result

    def test_no_user_data_keeps_template_unchanged(self):
        """When no user data, the template should be returned as-is."""
        ctx = UserScoringContext()
        result = PromptBuilder.build(ctx)
        # Should still have the researcher profile section
        assert "RESEARCHER PROFILE" in result

    def test_build_sanitizes_user_strings(self):
        """NFR-T5: user strings must be sanitized before injection."""
        ctx = UserScoringContext(
            thesis_title="Bad\nTitle\x00with\x1Fcontrol",
            thesis_question="Question\nwith\nnewlines",
        )
        result = PromptBuilder.build(ctx)
        assert "\x00" not in result
        assert "\x1F" not in result
        # User-supplied newlines are replaced with spaces by sanitize
        assert "Bad Titlewithcontrol" in result

    def test_no_cross_user_leak(self):
        """Two different users get different prompts."""
        ctx_a = UserScoringContext(thesis_title="User A Thesis")
        ctx_b = UserScoringContext(thesis_title="User B Thesis")
        result_a = PromptBuilder.build(ctx_a)
        result_b = PromptBuilder.build(ctx_b)
        assert result_a != result_b
        assert "User A Thesis" in result_a
        assert "User B Thesis" in result_b

    def test_empty_venues_fallback(self):
        ctx = UserScoringContext(thesis_title="Test Title", thesis_question="Test Q", tracked_venues=[])
        result = PromptBuilder.build(ctx)
        assert "none configured" in result

    def test_build_sanitizes_cluster_id(self):
        """NFR-T5: cluster id must be sanitized before injection into prompt."""
        ctx = UserScoringContext(
            scoring_clusters=[
                {"id": "evil\ninjection", "name": "Cluster", "description": "Desc.", "reward_level": "high"},
            ]
        )
        result = PromptBuilder.build(ctx)
        assert "\n" not in result
        assert "evil injection" in result  # sanitize() replaces \n with space
