from briefing import (
    assemble_content,
    build_briefing_messages,
    compact_articles,
    parse_briefing,
)


def _row(id, title, score, tags):
    return {
        "id": id, "title": title, "score": score, "feed_name": "Feed",
        "tags": tags, "summary_bullets": ["b1", "b2"], "url": f"http://x/{id}",
        "reading_time": 5, "read_at": None,
    }


def test_compact_keeps_essentials_only():
    out = compact_articles([_row(1, "T", 8.0, ["ebpf"])])
    assert out == [{"id": 1, "title": "T", "score": 8.0,
                    "feed_name": "Feed", "tags": ["ebpf"],
                    "summary_bullets": ["b1", "b2"]}]


def test_messages_have_system_and_user_with_language():
    msgs = build_briefing_messages([{"id": 1}], "français")
    assert msgs[0]["role"] == "system"
    assert "français" in msgs[0]["content"]
    assert "1" in msgs[1]["content"]  # the item id appears in the user payload


def test_parse_drops_unknown_ids_and_caps_top_picks():
    raw = {
        "intro": "x",
        "sections": [{"title": "S", "synthesis": "y", "why_it_matters": "z",
                      "article_ids": [1, 999]}],
        "top_picks": [1, 2, 3, 4],
    }
    parsed = parse_briefing(raw, valid_ids={1, 2, 3})
    assert parsed["sections"][0]["article_ids"] == [1]
    assert parsed["top_picks"] == [1, 2, 3]


def test_parse_returns_none_without_sections():
    assert parse_briefing({"intro": "x", "sections": []}, {1}) is None


def test_assemble_adds_denormalized_articles_map():
    parsed = {"intro": "i", "sections": [{"title": "S", "synthesis": "y",
              "why_it_matters": "z", "article_ids": [1]}], "top_picks": [1]}
    content = assemble_content(parsed, {1: _row(1, "T", 8.0, ["ebpf"])})
    assert content["articles"]["1"]["title"] == "T"
    assert content["intro"] == "i"
