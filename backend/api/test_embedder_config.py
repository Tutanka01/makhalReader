"""Tests for Story 14-1 — Configurable Embed Model.

Verifies:
- OLLAMA_EMBED_MODEL env var is read correctly (AC1).
- Fallback to nomic-embed-text when unset (AC2).
"""

import importlib
import os
import sys

_api_dir = os.path.join(os.path.dirname(__file__))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  ✅  {name}")


def _fail(name: str, msg: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  ❌  {name}: {msg}")


def test_custom_model_from_env() -> None:
    os.environ["OLLAMA_EMBED_MODEL"] = "paraphrase-multilingual-mpnet-base-v2"
    import embedder  # already imported, force re-eval
    importlib.reload(embedder)
    expected = "paraphrase-multilingual-mpnet-base-v2"
    actual = embedder.OLLAMA_EMBED_MODEL
    if actual == expected:
        _ok("custom_model_from_env")
    else:
        _fail("custom_model_from_env", f"expected {expected!r}, got {actual!r}")


def test_default_fallback() -> None:
    os.environ.pop("OLLAMA_EMBED_MODEL", None)
    import embedder
    importlib.reload(embedder)
    expected = "nomic-embed-text"
    actual = embedder.OLLAMA_EMBED_MODEL
    if actual == expected:
        _ok("default_fallback")
    else:
        _fail("default_fallback", f"expected {expected!r}, got {actual!r}")


def run_tests() -> None:
    global _PASS, _FAIL
    _PASS = 0
    _FAIL = 0

    tests = [
        ("custom_model_from_env", test_custom_model_from_env),
        ("default_fallback", test_default_fallback),
    ]
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            _fail(name, str(e))

    print(f"\n{'='*40}")
    print(f"  {_PASS}/{_PASS + _FAIL} passed")
    if _FAIL:
        print(f"  ❌  {_FAIL} FAILED")
    else:
        print(f"  ✅  ALL PASSED")


if __name__ == "__main__":
    run_tests()
