"""
Unit tests for backend/poller/paper_enricher.py

These tests are hermetic — they mock httpx.AsyncClient and never make real
network calls. They can run on the host (no Docker required).

Run with:
    source /tmp/basira-test-venv/bin/activate
    PYTHONPATH=backend/poller python -m pytest backend/scorer/tests/test_paper_enricher.py -v
"""
import asyncio
import json
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap: add poller to sys.path so we can import paper_enricher directly
# ---------------------------------------------------------------------------
_POLLER_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "backend", "poller"
)
sys.path.insert(0, os.path.abspath(_POLLER_DIR))

from paper_enricher import enrich_paper_meta, is_paper_url  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_client(ollama_json: dict) -> MagicMock:
    """Return an AsyncMock httpx.AsyncClient that always returns ollama_json."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = ollama_json

    client = AsyncMock()
    client.post = AsyncMock(return_value=mock_resp)
    return client


# ---------------------------------------------------------------------------
# is_paper_url tests
# ---------------------------------------------------------------------------

class TestIsPaperUrl(unittest.TestCase):
    def test_arxiv_abs_detected(self):
        self.assertTrue(is_paper_url("https://arxiv.org/abs/2401.12345"))

    def test_arxiv_with_version_detected(self):
        self.assertTrue(is_paper_url("https://arxiv.org/abs/2401.12345v2"))

    def test_semantic_scholar_detected(self):
        self.assertTrue(
            is_paper_url(
                "https://www.semanticscholar.org/paper/Attention-Is-All-You-Need/204e3073870fae3d05bcbc2f6a8e263d9b72e776"
            )
        )

    def test_openreview_detected(self):
        self.assertTrue(
            is_paper_url("https://openreview.net/forum?id=AbCdEf123")
        )

    def test_acl_anthology_detected(self):
        self.assertTrue(is_paper_url("https://aclanthology.org/2024.acl-long.1"))

    def test_doi_org_detected(self):
        self.assertTrue(is_paper_url("https://doi.org/10.18653/v1/2024.acl-long.1"))

    def test_blog_not_detected(self):
        self.assertFalse(is_paper_url("https://blog.example.com/my-post"))

    def test_hackernews_not_detected(self):
        self.assertFalse(is_paper_url("https://news.ycombinator.com/item?id=12345"))

    def test_github_not_detected(self):
        self.assertFalse(is_paper_url("https://github.com/org/repo"))

    def test_empty_string(self):
        self.assertFalse(is_paper_url(""))

    def test_arxiv_pdf_not_detected(self):
        # Only abs/ pages are in the pattern, not PDF links
        self.assertFalse(is_paper_url("https://arxiv.org/pdf/2401.12345"))


# ---------------------------------------------------------------------------
# enrich_paper_meta — non-paper URLs
# ---------------------------------------------------------------------------

class TestEnrichPaperMetaNonPaper(unittest.TestCase):
    def test_non_paper_returns_empty(self):
        """Non-paper URL must return {} in < 50ms, with no API calls."""
        import httpx
        client = MagicMock(spec=httpx.AsyncClient)
        result = run(
            enrich_paper_meta(
                "https://blog.example.com/post",
                {"content_text": "Some blog content"},
                client,
            )
        )
        self.assertEqual(result, {})
        client.post.assert_not_called()

    def test_hackernews_returns_empty(self):
        import httpx
        client = MagicMock(spec=httpx.AsyncClient)
        result = run(
            enrich_paper_meta(
                "https://news.ycombinator.com/item?id=999",
                {},
                client,
            )
        )
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# enrich_paper_meta — paper URL with no paper_meta from extractor
# ---------------------------------------------------------------------------

class TestEnrichPaperMetaFallback(unittest.TestCase):
    def test_paper_url_without_paper_meta_returns_fallback(self):
        """Paper URL but extractor returned no paper_meta → minimal fallback."""
        import httpx
        client = MagicMock(spec=httpx.AsyncClient)
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                {},  # no paper_meta key
                client,
            )
        )
        self.assertEqual(result, {"is_paper": True, "source": "fallback"})
        client.post.assert_not_called()

    def test_paper_url_is_paper_false_returns_fallback(self):
        """paper_meta present but is_paper=False → minimal fallback."""
        import httpx
        client = MagicMock(spec=httpx.AsyncClient)
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                {"paper_meta": {"is_paper": False}},
                client,
            )
        )
        self.assertEqual(result, {"is_paper": True, "source": "fallback"})

    def test_paper_url_no_abstract_returns_minimal(self):
        """is_paper=True but no abstract or content_text → returns partial dict."""
        import httpx
        client = MagicMock(spec=httpx.AsyncClient)
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                {
                    "paper_meta": {
                        "is_paper": True,
                        "source": "arxiv",
                        "paper_id": "2401.12345",
                    }
                },
                client,
            )
        )
        self.assertTrue(result["is_paper"])
        self.assertEqual(result["source"], "arxiv")
        # No Ollama call was needed — no abstract
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# enrich_paper_meta — successful Ollama classification
# ---------------------------------------------------------------------------

class TestEnrichPaperMetaOllamaSuccess(unittest.TestCase):
    def _make_extraction(self, abstract: str = "We propose a novel NLP method.") -> dict:
        return {
            "paper_meta": {
                "is_paper": True,
                "source": "arxiv",
                "paper_id": "2401.12345",
                "doi": "10.48550/arXiv.2401.12345",
                "abstract": abstract,
                "authors": ["Alice Smith"],
                "year": 2024,
                "methods": [],
                "datasets": [],
                "metrics": [],
                "fields_of_study": ["Computer Science"],
            },
            "content_text": abstract,
        }

    def test_classification_merged_into_paper_meta(self):
        """Ollama classification fields are merged into the returned dict."""
        client = _mock_client(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "contribution_type": "method",
                            "re_document_type": "none",
                            "confidence": 0.92,
                        }
                    )
                }
            }
        )
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                self._make_extraction(),
                client,
            )
        )
        self.assertEqual(result["contribution_type"], "method")
        self.assertEqual(result["re_document_type"], "none")
        self.assertAlmostEqual(result["confidence"], 0.92)
        self.assertTrue(result["is_paper"])
        self.assertEqual(result["source"], "arxiv")
        self.assertEqual(result["paper_id"], "2401.12345")

    def test_structural_metadata_preserved(self):
        """Original paper_meta fields survive the Ollama merge."""
        client = _mock_client(
            {
                "message": {
                    "content": '{"contribution_type": "survey", "re_document_type": "method", "confidence": 0.8}'
                }
            }
        )
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                self._make_extraction(),
                client,
            )
        )
        self.assertEqual(result["doi"], "10.48550/arXiv.2401.12345")
        self.assertEqual(result["authors"], ["Alice Smith"])
        self.assertEqual(result["year"], 2024)

    def test_ollama_called_once(self):
        """Exactly one Ollama chat call should be made per enrichment."""
        client = _mock_client(
            {
                "message": {
                    "content": '{"contribution_type": "empirical", "re_document_type": "elicitation", "confidence": 0.7}'
                }
            }
        )
        run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                self._make_extraction(),
                client,
            )
        )
        client.post.assert_called_once()
        call_args = client.post.call_args
        payload = call_args[1]["json"]
        self.assertEqual(payload["model"], os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
        self.assertFalse(payload["stream"])

    def test_abstract_truncated_to_2000_chars(self):
        """Abstracts longer than 2000 chars are truncated in the Ollama prompt."""
        long_abstract = "X" * 5000
        client = _mock_client(
            {
                "message": {
                    "content": '{"contribution_type": "theory", "re_document_type": "none", "confidence": 0.5}'
                }
            }
        )
        run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                self._make_extraction(abstract=long_abstract),
                client,
            )
        )
        call_args = client.post.call_args
        prompt_content = call_args[1]["json"]["messages"][0]["content"]
        # The prompt contains at most 2000 chars of the abstract
        self.assertNotIn("X" * 2001, prompt_content)


# ---------------------------------------------------------------------------
# enrich_paper_meta — Ollama failure (graceful degradation)
# ---------------------------------------------------------------------------

class TestEnrichPaperMetaOllamaFailure(unittest.TestCase):
    def test_ollama_network_error_does_not_raise(self):
        """Network error from Ollama must not propagate — returns structural data."""
        client = AsyncMock()
        client.post = AsyncMock(side_effect=ConnectionError("Ollama down"))

        extraction = {
            "paper_meta": {
                "is_paper": True,
                "source": "arxiv",
                "paper_id": "2401.12345",
                "abstract": "A method for something.",
            }
        }
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.12345",
                extraction,
                client,
            )
        )
        # Should return paper_meta without classification fields
        self.assertTrue(result["is_paper"])
        self.assertEqual(result["source"], "arxiv")
        self.assertNotIn("contribution_type", result)

    def test_ollama_bad_json_does_not_raise(self):
        """Malformed JSON from Ollama must not propagate."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Sorry, I can't classify that."}
        }
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_resp)

        extraction = {
            "paper_meta": {
                "is_paper": True,
                "source": "semanticscholar",
                "paper_id": "abc123",
                "abstract": "Some abstract.",
            }
        }
        result = run(
            enrich_paper_meta(
                "https://www.semanticscholar.org/paper/slug/abc123",
                extraction,
                client,
            )
        )
        self.assertTrue(result["is_paper"])
        self.assertEqual(result["source"], "semanticscholar")
        self.assertNotIn("contribution_type", result)

    def test_ollama_markdown_fenced_json_parsed(self):
        """Ollama sometimes wraps JSON in markdown fences — strip and parse."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "message": {
                "content": '```json\n{"contribution_type": "benchmark", "re_document_type": "none", "confidence": 0.85}\n```'
            }
        }
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_resp)

        extraction = {
            "paper_meta": {
                "is_paper": True,
                "source": "arxiv",
                "paper_id": "2401.99999",
                "abstract": "We benchmark N models.",
            }
        }
        result = run(
            enrich_paper_meta(
                "https://arxiv.org/abs/2401.99999",
                extraction,
                client,
            )
        )
        self.assertEqual(result["contribution_type"], "benchmark")
        self.assertAlmostEqual(result["confidence"], 0.85)


# ---------------------------------------------------------------------------
# enrich_paper_meta — content_text fallback for abstract
# ---------------------------------------------------------------------------

class TestEnrichPaperMetaContentTextFallback(unittest.TestCase):
    def test_content_text_used_when_no_abstract(self):
        """If paper_meta has no abstract, content_text is used for Ollama."""
        client = _mock_client(
            {
                "message": {
                    "content": '{"contribution_type": "position", "re_document_type": "none", "confidence": 0.6}'
                }
            }
        )
        result = run(
            enrich_paper_meta(
                "https://aclanthology.org/2024.acl-long.1",
                {
                    "paper_meta": {
                        "is_paper": True,
                        "source": "acl",
                        "paper_id": "2024.acl-long.1",
                        # No "abstract" key
                    },
                    "content_text": "We argue that position papers are undervalued.",
                },
                client,
            )
        )
        self.assertEqual(result["contribution_type"], "position")
        client.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
