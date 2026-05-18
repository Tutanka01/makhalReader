import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.getenv("DB_PATH", "/data/basira.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, default="General")
    active = Column(Boolean, default=True, nullable=False)
    last_fetched = Column(DateTime, nullable=True)


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    feed_id = Column(Integer, ForeignKey("feeds.id"), nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    published_at = Column(DateTime, nullable=True)
    author = Column(String, nullable=True)
    content_html = Column(Text, nullable=True)
    content_text = Column(Text, nullable=True)
    images_json = Column(Text, default="[]", nullable=False)
    score = Column(Float, nullable=True)
    tags_json = Column(Text, default="[]", nullable=False)
    summary_bullets_json = Column(Text, default="[]", nullable=False)
    reason = Column(String, nullable=True)
    read_at = Column(DateTime, nullable=True)
    bookmarked = Column(Boolean, default=False, nullable=False)
    extraction_failed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    title_fingerprint = Column(String(16), nullable=True, index=True)
    user_feedback = Column(Integer, nullable=True)  # 1=like, -1=dislike, NULL=no feedback

    # Research dimensions — populated by scorer (Story 2.1).
    # These columns were silently missing from api/database.py (fixed in Story 2.2).
    score_meta_json = Column(Text, nullable=True)
    contribution_type = Column(String(24), nullable=True)
    re_document_type = Column(String(24), nullable=True)

    # Paper enrichment — populated by poller before scoring (Story 2.2).
    paper_meta_json = Column(Text, nullable=True)

    # Embedding index — set to 1 once indexed in ChromaDB (Story 3.1).
    embedding_indexed = Column(Integer, default=0, nullable=True)

    __table_args__ = (
        Index("ix_articles_title_fp_created", "title_fingerprint", "created_at"),
    )


class Highlight(Base):
    __tablename__ = "highlights"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    selected_text = Column(Text, nullable=False)
    prefix_context = Column(Text, nullable=False, default="")
    suffix_context = Column(Text, nullable=False, default="")
    color = Column(String(16), nullable=False, default="yellow")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_highlights_article_id", "article_id"),
    )


class ResearchProfile(Base):
    """Typed researcher profile entries — topics, methods, domains, avoidances."""
    __tablename__ = "research_profile"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(24), nullable=False)   # 'topic'|'method'|'domain'|'avoid'
    label = Column(String(256), nullable=False)
    weight = Column(Float, default=1.0, nullable=False)
    source = Column(String(24), default="manual", nullable=False)  # 'manual'|'feedback'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("kind", "label", name="ux_research_profile"),
    )


class LiteratureReview(Base):
    """Persisted literature-review synthesis (Story 3.4)."""
    __tablename__ = "literature_reviews"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(Text, nullable=False)
    window_days = Column(Integer, nullable=False)
    min_rigor = Column(Float, default=0.0, nullable=False)
    body_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AuthSession(Base):
    """Persistent login sessions. One row per active login."""
    __tablename__ = "auth_sessions"

    id = Column(String(64), primary_key=True)          # secrets.token_hex(32)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    last_seen = Column(DateTime, nullable=True)
    user_agent = Column(String(500), nullable=True)
    remember_me = Column(Boolean, default=False, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Additive migrations — safe to run multiple times.
    _migrations = [
        "ALTER TABLE articles ADD COLUMN title_fingerprint VARCHAR(16)",
        "ALTER TABLE articles ADD COLUMN user_feedback INTEGER",
        "CREATE TABLE IF NOT EXISTS highlights (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, selected_text TEXT NOT NULL, prefix_context TEXT NOT NULL DEFAULT '', suffix_context TEXT NOT NULL DEFAULT '', color VARCHAR(16) NOT NULL DEFAULT 'yellow', note TEXT, created_at DATETIME NOT NULL)",
        "CREATE INDEX IF NOT EXISTS ix_highlights_article_id ON highlights(article_id)",
        # Story 2.1 columns (were only in shared/database.py — fixed here in Story 2.2)
        "ALTER TABLE articles ADD COLUMN score_meta_json TEXT",
        "ALTER TABLE articles ADD COLUMN contribution_type VARCHAR(24)",
        "ALTER TABLE articles ADD COLUMN re_document_type VARCHAR(24)",
        # Story 2.2 column
        "ALTER TABLE articles ADD COLUMN paper_meta_json TEXT",
        # Story 3.1 column
        "ALTER TABLE articles ADD COLUMN embedding_indexed INTEGER DEFAULT 0",
        # Story 3.3 table + unique index
        "CREATE TABLE IF NOT EXISTS research_profile (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, label TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0, source TEXT NOT NULL DEFAULT 'manual', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile ON research_profile(kind, label)",
        # Story 3.4 — literature review persistence
        "CREATE TABLE IF NOT EXISTS literature_reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, window_days INTEGER NOT NULL, min_rigor REAL NOT NULL DEFAULT 0.0, body_json TEXT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    ]
    with engine.connect() as conn:
        for stmt in _migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
