import json
from typing import Optional

MAX_TITLE = 160
MAX_BULLET = 180


def compact_articles(rows: list[dict]) -> list[dict]:
    """Reduce article rows to the minimum the LLM needs to cluster + synthesize."""
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "title": (r["title"] or "")[:MAX_TITLE],
            "score": r["score"],
            "feed_name": r.get("feed_name", ""),
            "tags": (r.get("tags") or [])[:5],
            "summary_bullets": [b[:MAX_BULLET] for b in (r.get("summary_bullets") or [])[:3]],
        })
    return out


_SYSTEM_TEMPLATE = (
    "Tu es l'éditeur de briefing de MakhalReader, pour un ingénieur SRE/infra/IA.\n"
    "On te donne les meilleurs articles techniques des dernières 24h (métadonnées compactes).\n"
    "Produis un briefing matinal en {language}, dense et sans bla-bla.\n\n"
    "Règles:\n"
    "- Regroupe les articles par THÈME (3 à 6 sections). Ne crée pas une section par article.\n"
    "- Pour chaque section: un titre court, une synthèse d'un paragraphe (ce qui se passe, "
    "ce qui est nouveau vs déjà-vu), et une phrase 'pourquoi ça compte'.\n"
    "- Identifie les tendances transversales entre sources.\n"
    "- Choisis AU PLUS 3 articles à vraiment ouvrir aujourd'hui (top_picks), les plus denses.\n"
    "- N'invente aucun fait: utilise seulement les métadonnées fournies.\n"
    "- Réfère les articles par leur id numérique uniquement.\n\n"
    "Réponds avec un UNIQUE objet JSON valide, sans texte autour, de cette forme:\n"
    '{{"intro": "1-2 phrases", "sections": [{{"title": "...", "synthesis": "...", '
    '"why_it_matters": "...", "article_ids": [12, 45]}}], "top_picks": [45, 12, 78]}}'
)


def build_briefing_messages(items: list[dict], language: str) -> list[dict]:
    user = (
        f"Articles ({len(items)}), triés par score décroissant:\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": _SYSTEM_TEMPLATE.format(language=language)},
        {"role": "user", "content": user},
    ]


def _clean_ids(ids, valid_ids: set[int]) -> list[int]:
    seen, out = set(), []
    for x in ids if isinstance(ids, list) else []:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i in valid_ids and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def parse_briefing(raw: dict, valid_ids: set[int]) -> Optional[dict]:
    """Validate the LLM output. Returns a clean dict or None if structurally unusable."""
    if not isinstance(raw, dict):
        return None
    sections_in = raw.get("sections")
    if not isinstance(sections_in, list) or not sections_in:
        return None

    sections = []
    for s in sections_in:
        if not isinstance(s, dict):
            continue
        ids = _clean_ids(s.get("article_ids"), valid_ids)
        if not ids:
            continue
        sections.append({
            "title": str(s.get("title", "")).strip()[:120] or "Sans titre",
            "synthesis": str(s.get("synthesis", "")).strip()[:1200],
            "why_it_matters": str(s.get("why_it_matters", "")).strip()[:300],
            "article_ids": ids,
        })
    if not sections:
        return None

    return {
        "intro": str(raw.get("intro", "")).strip()[:600],
        "sections": sections,
        "top_picks": _clean_ids(raw.get("top_picks"), valid_ids)[:3],
    }


def assemble_content(parsed: dict, articles_by_id: dict[int, dict]) -> dict:
    """Attach a denormalized snapshot of every referenced article (self-contained briefing)."""
    referenced: set[int] = set(parsed.get("top_picks", []))
    for s in parsed["sections"]:
        referenced.update(s["article_ids"])

    articles = {}
    for aid in referenced:
        r = articles_by_id.get(aid)
        if not r:
            continue
        articles[str(aid)] = {
            "id": r["id"],
            "title": r["title"],
            "url": r["url"],
            "score": r["score"],
            "feed_name": r.get("feed_name", ""),
            "tags": (r.get("tags") or [])[:5],
            "summary_bullets": (r.get("summary_bullets") or [])[:3],
            "reading_time": r.get("reading_time"),
            "read_at": r.get("read_at"),
        }
    return {
        "intro": parsed["intro"],
        "sections": parsed["sections"],
        "top_picks": parsed["top_picks"],
        "articles": articles,
    }
