import os
from pathlib import Path

_PROFILE = os.getenv("PROMPT_PROFILE", "unified")
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PROMPT_FILE = _PROMPTS_DIR / f"{_PROFILE}.md"

if not _PROMPT_FILE.exists():
    raise FileNotFoundError(
        f"Prompt profile '{_PROFILE}' not found at {_PROMPT_FILE}. "
        f"Valid profiles: {[p.stem for p in _PROMPTS_DIR.glob('*.md')]}"
    )

SYSTEM_PROMPT: str = _PROMPT_FILE.read_text(encoding="utf-8")
