from llm import extract_json


def test_extracts_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extracts_json_from_markdown_fence():
    text = 'Here you go:\n```json\n{"intro": "x", "sections": []}\n```\nthanks'
    assert extract_json(text) == {"intro": "x", "sections": []}


def test_strips_trailing_commas():
    assert extract_json('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}


def test_returns_none_on_garbage():
    assert extract_json("no json at all") is None
