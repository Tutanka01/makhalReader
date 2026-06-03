"""PromptBuilder — renders a user-specific scoring prompt (Story 5.1, FR-MT-26)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PROFILE_HEADERS = ["## RESEARCHER PROFILE", "## RESEARCH PROFILE"]
_CLUSTERS_PREFIX = "## TOPIC TAXONOMY"

_TEMPLATE_CACHE: Dict[str, str] = {}


@dataclass
class UserScoringContext:
    thesis_title: str = ""
    thesis_question: str = ""
    tracked_venues: List[str] = field(default_factory=list)
    scoring_clusters: List[Dict] = field(default_factory=list)
    avoid_topics: List[str] = field(default_factory=list)
    prompt_profile: str = "unified"
    thesis_contribution: Optional[str] = None


def sanitize(text: str) -> str:
    """NFR-T5: strip control chars, newlines; trim whitespace."""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    return text.replace("\n", " ").replace("\r", " ").strip()


def _load_template(profile: str) -> str:
    if profile not in _TEMPLATE_CACHE:
        path = _PROMPTS_DIR / f"{profile}.md"
        if not path.exists():
            path = _PROMPTS_DIR / "unified.md"
        _TEMPLATE_CACHE[profile] = path.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE[profile]


def _replace_section(template: str, header_prefix: str, new_content: str) -> str:
    """Replace a markdown section from `header_prefix` to the next `##` or EOF."""
    pattern = re.escape(header_prefix) + r".*?(?=\n## |\Z)"
    match = re.search(pattern, template, re.DOTALL)
    if match:
        return template[: match.start()] + new_content + template[match.end() :]
    return template


def _has_user_data(ctx: UserScoringContext) -> bool:
    return bool(ctx.thesis_title or ctx.thesis_question or ctx.tracked_venues)


def _replace_profile_section(template: str, ctx: UserScoringContext) -> str:
    if not _has_user_data(ctx):
        return template
    venues_str = (
        ", ".join(sanitize(v) for v in ctx.tracked_venues) + "."
        if ctx.tracked_venues
        else "(none configured)."
    )
    new_profile = (
        "## RESEARCHER PROFILE\n"
        "\n"
        f'**Thesis title:** "{sanitize(ctx.thesis_title)}"\n'
        "\n"
        f"**Central thesis question:** {sanitize(ctx.thesis_question)}\n"
        "\n"
        "**Languages:** French and English \u2014 both equally valid.\n"
        "\n"
        f"**Tracked venues:** {venues_str}\n"
    )
    for h in _PROFILE_HEADERS:
        result = _replace_section(template, h, new_profile)
        if result != template:
            return result
    return template


def _replace_clusters_section(template: str, ctx: UserScoringContext) -> str:
    """Replace the clusters section with user-specific clusters when available."""
    if not ctx.scoring_clusters:
        return template
    lines = [
        "\n## TOPIC TAXONOMY \u2014 5 CORE CLUSTERS\n",
    ]
    for c in ctx.scoring_clusters:
        name = sanitize(c.get("name", ""))
        desc = sanitize(c.get("description", ""))
        reward = c.get("reward_level", "high")
        cid = c.get("id", "?")
        lines.append(f"### [Cluster {cid}] {name} ({reward.title()} reward)")
        lines.append(desc)
        lines.append("")
    new_section = "\n".join(lines)
    return _replace_section(template, _CLUSTERS_PREFIX, new_section)


class PromptBuilder:
    """Builds a user-specific scoring prompt from a template + user context."""

    @staticmethod
    def build(ctx: UserScoringContext) -> str:
        template = _load_template(ctx.prompt_profile)
        template = _replace_profile_section(template, ctx)
        template = _replace_clusters_section(template, ctx)
        return template
