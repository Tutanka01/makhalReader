"""
Static conference data with countdown computation.

No DB table required — just Python data + settings table for bookmarks.
Update this file each September when major venue deadlines are announced.
"""
from datetime import date

CONFERENCES = [
    {
        "venue": "ICSE 2027",
        "track": "Research",
        "abstract_deadline": "2026-08-30",
        "paper_deadline": "2026-09-06",
        "notification_date": "2026-12-10",
        "conference_date": "2027-04-12",
        "url": "https://conf.researchr.org/home/icse-2027",
        "note": "Primary SE venue",
    },
    {
        "venue": "RE 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2027-03-15",
        "notification_date": "2027-05-15",
        "conference_date": "2027-09-15",
        "url": "https://requirements-engineering.org",
        "note": "Core thesis venue",
    },
    {
        "venue": "MODELS 2026",
        "track": "Research",
        "abstract_deadline": "2026-05-10",
        "paper_deadline": "2026-05-17",
        "notification_date": "2026-07-14",
        "conference_date": "2026-10-01",
        "url": "https://conf.researchr.org/home/models-2026",
        "note": "MBSE core venue",
    },
    {
        "venue": "CAiSE 2027",
        "track": "Research",
        "abstract_deadline": "2026-11-15",
        "paper_deadline": "2026-11-22",
        "notification_date": "2027-02-01",
        "conference_date": "2027-06-07",
        "url": "https://caise2027.org",
        "note": "Information systems & SE",
    },
    {
        "venue": "REFSQ 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2026-10-15",
        "notification_date": "2026-12-15",
        "conference_date": "2027-04-07",
        "url": "https://refsq.org",
        "note": "Requirements engineering focus",
    },
    {
        "venue": "ECMFA 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2027-02-15",
        "notification_date": "2027-04-01",
        "conference_date": "2027-06-15",
        "url": "https://ecmfa.org",
        "note": "Model-driven engineering",
    },
    {
        "venue": "INCOSE IS 2027",
        "track": "Research",
        "abstract_deadline": "2026-11-01",
        "paper_deadline": "2026-11-15",
        "notification_date": "2027-01-15",
        "conference_date": "2027-06-28",
        "url": "https://www.incose.org/symp2027",
        "note": "Systems engineering core venue",
    },
    {
        "venue": "NeurIPS 2026",
        "track": "Research",
        "abstract_deadline": "2026-05-15",
        "paper_deadline": "2026-05-22",
        "notification_date": "2026-09-25",
        "conference_date": "2026-12-06",
        "url": "https://neurips.cc",
        "note": "AI methods — foundation models",
    },
    {
        "venue": "ICLR 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2026-10-01",
        "notification_date": "2027-01-22",
        "conference_date": "2027-05-01",
        "url": "https://iclr.cc",
        "note": "LLM architecture research",
    },
    {
        "venue": "ACL 2027",
        "track": "Research",
        "abstract_deadline": "2026-12-08",
        "paper_deadline": "2026-12-15",
        "notification_date": "2027-03-15",
        "conference_date": "2027-07-27",
        "url": "https://2027.aclweb.org",
        "note": "NLP — NLP4RE papers",
    },
]


def get_conferences_with_countdown(bookmarked_venues: set[str] | None = None) -> list[dict]:
    """Compute countdowns for all conferences and sort by paper deadline ascending."""
    today = date.today()
    bookmarked = bookmarked_venues or set()
    result = []
    for conf in CONFERENCES:
        paper_dl = date.fromisoformat(conf["paper_deadline"])
        abstract_dl = date.fromisoformat(conf["abstract_deadline"]) if conf.get("abstract_deadline") else None
        days_to_paper = (paper_dl - today).days
        days_to_abstract = (abstract_dl - today).days if abstract_dl else None
        result.append({
            "venue": conf["venue"],
            "track": conf["track"],
            "abstract_deadline": conf["abstract_deadline"],
            "paper_deadline": conf["paper_deadline"],
            "notification_date": conf.get("notification_date"),
            "conference_date": conf["conference_date"],
            "url": conf["url"],
            "note": conf.get("note"),
            "days_to_abstract": days_to_abstract,
            "days_to_paper": days_to_paper,
            "is_past": days_to_paper < 0,
            "bookmarked": conf["venue"] in bookmarked,
        })
    return sorted(result, key=lambda c: (not c["bookmarked"], c["paper_deadline"]))
