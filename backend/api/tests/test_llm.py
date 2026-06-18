import llm
from llm import extract_json


def test_resolve_provider_prefers_explicit_openai_endpoint(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BASE_URL", "https://my-host/v1")
    monkeypatch.setattr(llm, "LLM_API_KEY", "k")
    monkeypatch.setattr(llm, "LLM_MODEL", "m")
    monkeypatch.setattr(llm, "OPENROUTER_API_KEY", "sk-should-be-ignored")
    kind, url, key, model = llm.resolve_provider()
    assert kind == "openai"
    assert url == "https://my-host/v1/chat/completions"
    assert key == "k" and model == "m"


def test_resolve_provider_falls_back_to_openrouter(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm, "OPENROUTER_API_KEY", "sk-abc")
    monkeypatch.setattr(llm, "QA_MODEL", "qa")
    kind, url, key, model = llm.resolve_provider()
    assert kind == "openai"
    assert "openrouter.ai" in url
    assert key == "sk-abc" and model == "qa"


def test_resolve_provider_defaults_to_ollama(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BASE_URL", "")
    monkeypatch.setattr(llm, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://ollama:11434")
    monkeypatch.setattr(llm, "OLLAMA_MODEL", "mistral")
    kind, url, key, model = llm.resolve_provider()
    assert kind == "ollama"
    assert url == "http://ollama:11434" and model == "mistral"


def test_chat_completions_url_is_forgiving():
    assert llm._chat_completions_url("https://h/v1") == "https://h/v1/chat/completions"
    assert llm._chat_completions_url("https://h/v1/") == "https://h/v1/chat/completions"
    assert llm._chat_completions_url("https://h/v1/chat/completions") == "https://h/v1/chat/completions"


def test_extracts_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extracts_json_from_markdown_fence():
    text = 'Here you go:\n```json\n{"intro": "x", "sections": []}\n```\nthanks'
    assert extract_json(text) == {"intro": "x", "sections": []}


def test_strips_trailing_commas():
    assert extract_json('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}


def test_returns_none_on_garbage():
    assert extract_json("no json at all") is None
