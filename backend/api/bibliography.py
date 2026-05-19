"""
BibTeX bibliography generator for Baṣīra.

Generates `.bib` files from the article corpus for use in Overleaf / LaTeX.
"""
import json
import re
import unicodedata
from datetime import date


def generate_bibtex(articles: list) -> str:
    """Generate a complete BibTeX string from a list of article ORM rows."""
    entries: list[str] = []
    for article in articles:
        key = _make_bibtex_key(article)
        authors = _format_authors(article)
        year = _extract_year(article)
        doi = _extract_doi(article)
        title = _bibtex_escape(article.title)

        lines = [f"@article{{{key},"]
        lines.append(f"  author = {{{authors}}},")
        lines.append(f"  title = {{{title}}},")
        if year:
            lines.append(f"  year = {{{year}}},")
        lines.append(f"  url = {{{_bibtex_escape(article.url)}}},")
        lines.append(f"  journal = {{Baṣīra Corpus}},")
        if doi:
            lines.append(f"  doi = {{{doi}}},")
        lines.append("}")
        entries.append("\n".join(lines))

    return "\n\n".join(entries) + "\n"


def _make_bibtex_key(article) -> str:
    """Create a BibTeX citation key: authorYearTitle (lowercase, no spaces)."""
    author_part = _first_author_lastname(article) or article.title.strip()[:10]
    year = _extract_year(article) or "unknown"
    title_slug = re.sub(r"[^a-zA-Z0-9]", "", article.title)[:20]
    raw = f"{author_part}{year}{title_slug}"[:64]
    return _slugify(raw)


def _first_author_lastname(article) -> str | None:
    """Extract the last name of the first author from paper_meta_json or article.author."""
    authors = _extract_author_list(article)
    if not authors:
        return None
    name = authors[0].strip()
    # Last name is the last word in the name for Western conventions
    parts = name.split()
    return parts[-1] if len(parts) > 1 else name


def _extract_author_list(article) -> list[str]:
    """Get the list of author names from paper_meta_json or fallback to article.author."""
    if article.paper_meta_json:
        try:
            parsed = json.loads(article.paper_meta_json)
            raw = parsed.get("authors") or []
            if raw and isinstance(raw[0], dict):
                return [a.get("name", "") for a in raw if a.get("name")]
            if raw and isinstance(raw[0], str):
                return raw
        except (json.JSONDecodeError, TypeError, IndexError):
            pass
    if article.author:
        return [article.author]
    return []


def _format_authors(article) -> str:
    """Format authors for BibTeX: 'Last, First and Last, First'."""
    names = _extract_author_list(article)
    if not names:
        # Fallback: use title as author placeholder
        return _bibtex_escape(article.title)

    formatted: list[str] = []
    for name in names:
        parts = name.strip().split()
        if len(parts) >= 2:
            last = parts[-1]
            first = " ".join(parts[:-1])
            formatted.append(f"{last}, {first}")
        else:
            formatted.append(parts[0])

    return " and ".join(_bibtex_escape(f) for f in formatted)


def _extract_year(article) -> str | None:
    """Extract the publication year from paper_meta_json or published_at."""
    if article.paper_meta_json:
        try:
            parsed = json.loads(article.paper_meta_json)
            y = parsed.get("year")
            if y:
                return str(int(y))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if article.published_at:
        return str(article.published_at.year)
    return None


def _extract_doi(article) -> str | None:
    """Extract the DOI from paper_meta_json."""
    if not article.paper_meta_json:
        return None
    try:
        parsed = json.loads(article.paper_meta_json)
        doi = parsed.get("doi")
        if doi and isinstance(doi, str) and doi.strip():
            return doi.strip()
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _bibtex_escape(text: str) -> str:
    """Escape special BibTeX characters."""
    replacements = {
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
    return text


def _slugify(text: str) -> str:
    """Convert text to a lowercase ASCII slug for BibTeX keys."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]", "", text)
    text = text.lower()
    return text[:64]
