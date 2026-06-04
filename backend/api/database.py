from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import bcrypt
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
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @classmethod
    def lookup_invite_code(cls, db: Session, code: str):
        return db.query(cls).filter(cls.code == code).first()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    role = Column(String, nullable=False, default="member")
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    onboarding_done = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @classmethod
    def register(cls, db: Session, email: str, password: str, display_name: str | None = None, org_id: int | None = None):
        existing = db.query(cls).filter(cls.email == email).first()
        if existing:
            return None
        pwd_hash = bcrypt.hashpw(
            hashlib.sha256(password.encode()).digest(),
            bcrypt.gensalt(rounds=12),
        )
        user = cls(
            email=email,
            password_hash=pwd_hash.decode(),
            display_name=display_name,
            org_id=org_id,
        )
        db.add(user)
        db.commit()
        return user

    @classmethod
    def authenticate(cls, db: Session, email: str, password: str):
        user = db.query(cls).filter(cls.email == email).first()
        if not user:
            return None
        digest = hashlib.sha256(password.encode()).digest()
        if bcrypt.checkpw(digest, user.password_hash.encode()):
            return user
        return None


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
    tracked_author_alert = Column(Boolean, default=False, nullable=False)

    # Story 5.5 — citation graph
    ss_paper_id = Column(String(64), nullable=True, index=True)
    cited_by_corpus_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_articles_title_fp_created", "title_fingerprint", "created_at"),
    )


class ArticleScore(Base):
    """Per-user per-article scoring and engagement data (Story 2.1, FR-MT-7/12)."""
    __tablename__ = "article_scores"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    score = Column(Float, nullable=True)
    tags_json = Column(Text, default="[]", nullable=False)
    summary_bullets_json = Column(Text, default="[]", nullable=False)
    reason = Column(String, nullable=True)
    read_at = Column(DateTime, nullable=True)
    bookmarked = Column(Boolean, default=False, nullable=False)
    user_feedback = Column(Integer, nullable=True)
    contribution_type = Column(String(24), nullable=True)
    re_document_type = Column(String(24), nullable=True)
    score_meta_json = Column(Text, nullable=True)
    facets_json = Column(Text, nullable=True)  # Story 10.1 — per-article facets result
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class UserFeedSubscription(Base):
    """User-to-feed subscription (Story 3.1, FR-MT-13)."""
    __tablename__ = "user_feed_subscriptions"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    feed_id = Column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class UserConfig(Base):
    """Per-user tenant configuration (Story 4.1, FR-MT-19)."""
    __tablename__ = "user_config"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    thesis_title = Column(String, nullable=False, default="")
    thesis_question = Column(String, nullable=True)
    thesis_contribution = Column(String, nullable=True)
    thesis_sections_json = Column(Text, nullable=False, default="[]")
    scoring_clusters_json = Column(Text, nullable=False, default="[]")
    tracked_venues_json = Column(Text, nullable=False, default="[]")
    avoid_topics_json = Column(Text, nullable=False, default="[]")
    weekly_goal = Column(Integer, nullable=False, default=10)
    model_preference = Column(String, nullable=False, default="google/gemini-flash-1.5")
    prompt_profile = Column(String, nullable=False, default="unified")
    prompt_cache_text = Column(Text, nullable=True)
    prompt_cache_hash = Column(String(64), nullable=True)
    facet_schema_json = Column(Text, nullable=True)  # Story 10.1 — per-tenant facet schema
    # Story 11.2 — bootstrap config (thesis-driven config generation)
    thesis_text = Column(Text, nullable=True)
    domain_label = Column(String(128), nullable=True)
    bootstrap_hash = Column(String(64), nullable=True)
    bootstrap_model = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class UserSetting(Base):
    """Per-user key-value settings (FR-MT-38 / Story 6.5)."""
    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Highlight(Base):
    __tablename__ = "highlights"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    selected_text = Column(Text, nullable=False)
    prefix_context = Column(Text, nullable=False, default="")
    suffix_context = Column(Text, nullable=False, default="")
    color = Column(String(16), nullable=False, default="yellow")
    note = Column(Text, nullable=True)
    thesis_section = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_highlights_article_id", "article_id"),
    )


class ResearchProfile(Base):
    """Typed researcher profile entries — topics, methods, domains, avoidances."""
    __tablename__ = "research_profile"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    kind = Column(String(24), nullable=False)   # 'topic'|'method'|'domain'|'avoid'
    label = Column(String(256), nullable=False)
    weight = Column(Float, default=1.0, nullable=False)
    source = Column(String(24), default="manual", nullable=False)  # 'manual'|'feedback'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "kind", "label", name="ux_research_profile"),
    )


class LiteratureReview(Base):
    """Persisted literature-review synthesis (Story 3.4)."""
    __tablename__ = "literature_reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class ThesisContribution(Base):
    """Singleton row storing the researcher's thesis contribution statement."""
    __tablename__ = "thesis_contribution"

    id = Column(Integer, primary_key=True, default=1)
    statement = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class NoveltyAlert(Base):
    """Per-article threat assessment against the thesis contribution."""
    __tablename__ = "novelty_alerts"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    overlap_score = Column(Float, nullable=False)
    positioning_note = Column(Text, nullable=False)
    checked_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("article_id", "user_id", name="ux_novelty_alert_article_user"),
    )


class TrackedAuthor(Base):
    """Authors automatically tracked from high-scored papers (Story 5.2)."""
    __tablename__ = "tracked_authors"

    id = Column(Integer, primary_key=True, index=True)
    ss_author_id = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    paper_count = Column(Integer, default=0, nullable=False)
    avg_score = Column(Float, default=0.0, nullable=False)
    alert_count = Column(Integer, default=0, nullable=False)
    last_checked = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user_id = Column(Integer, nullable=False)


def get_setting(db: Session, key: str, default: str = "") -> str:
    """Read a key from the settings table. Returns default if missing."""
    from sqlalchemy import text as _text
    row = db.execute(_text("SELECT value FROM settings WHERE key = :k"), {"k": key}).fetchone()
    return row[0] if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    """Upsert a key into the settings table."""
    from sqlalchemy import text as _text
    db.execute(
        _text("INSERT OR REPLACE INTO settings (key, value) VALUES (:k, :v)"),
        {"k": key, "v": value},
    )
    db.commit()


def get_user_setting(db: Session, user_id: int, key: str, default: str = "") -> str:
    """Read a per-user setting. Returns default if missing."""
    row = db.query(UserSetting).filter_by(user_id=user_id, key=key).first()
    return row.value if row else default


def set_user_setting(db: Session, user_id: int, key: str, value: str) -> None:
    """Upsert a per-user setting."""
    row = db.query(UserSetting).filter_by(user_id=user_id, key=key).first()
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(UserSetting(user_id=user_id, key=key, value=value))
    db.commit()


def _seed_default_user():
    """Auto-create seed user_id=1 when AUTH_PASSWORD is set and users table is empty."""
    raw = os.getenv("AUTH_PASSWORD", "")
    if not raw:
        return
    from sqlalchemy import text as _text
    try:
        db = SessionLocal()
        existing = db.query(User).count()
        if existing > 0:
            return
        pwd_hash = bcrypt.hashpw(
            hashlib.sha256(raw.encode()).digest(),
            bcrypt.gensalt(rounds=12),
        )
        user = User(
            email="admin@basira.local",
            password_hash=pwd_hash.decode(),
            display_name="Admin",
            role="admin",
            onboarding_done=True,
        )
        db.add(user)
        db.commit()
        print(f"[init_db] Seed user created: id={user.id}")
    except Exception:
        pass
    finally:
        db.close()


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
        # Story 4.2 — research_profile user_id column (FR-MT-20)
        "ALTER TABLE research_profile ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "DROP INDEX IF EXISTS ux_research_profile",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile ON research_profile(user_id, kind, label)",
        # Story 3.4 — literature review persistence
        "CREATE TABLE IF NOT EXISTS literature_reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, window_days INTEGER NOT NULL, min_rigor REAL NOT NULL DEFAULT 0.0, body_json TEXT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        # Story 5.1 / 5.4 — settings key-value store (shared across Epic 5)
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        # Story 5.1 — thesis contribution (singleton, id=1)
        "CREATE TABLE IF NOT EXISTS thesis_contribution (id INTEGER PRIMARY KEY DEFAULT 1, statement TEXT NOT NULL, updated_at DATETIME NOT NULL)",
        # Story 5.1 — novelty threat alerts
        "CREATE TABLE IF NOT EXISTS novelty_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, overlap_score REAL NOT NULL, positioning_note TEXT NOT NULL, checked_at DATETIME NOT NULL)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_novelty_alert_article ON novelty_alerts(article_id)",
        # Story 5.2 — author radar
        "CREATE TABLE IF NOT EXISTS tracked_authors (id INTEGER PRIMARY KEY AUTOINCREMENT, ss_author_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, paper_count INTEGER NOT NULL DEFAULT 0, avg_score REAL NOT NULL DEFAULT 0.0, alert_count INTEGER NOT NULL DEFAULT 0, last_checked DATETIME, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "CREATE INDEX IF NOT EXISTS ix_tracked_authors_ss_author_id ON tracked_authors(ss_author_id)",
        "ALTER TABLE articles ADD COLUMN tracked_author_alert BOOLEAN DEFAULT 0",
        # Story 5.3 — thesis section on highlights
        "ALTER TABLE highlights ADD COLUMN thesis_section TEXT",
        # Story 6.1 — highlights user_id (FR-MT-34)
        "ALTER TABLE highlights ADD COLUMN user_id INTEGER REFERENCES users(id)",
        # Story 6.2 — literature reviews user_id (FR-MT-35)
        "ALTER TABLE literature_reviews ADD COLUMN user_id INTEGER REFERENCES users(id)",
        # Story 6.3 — novelty alerts user_id (FR-MT-36)
        "ALTER TABLE novelty_alerts ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "DROP INDEX IF EXISTS ux_novelty_alert_article",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_novelty_alert_article_user ON novelty_alerts(article_id, user_id)",
        # Story 6.4 — tracked authors user_id (FR-MT-37)
        "ALTER TABLE tracked_authors ADD COLUMN user_id INTEGER REFERENCES users(id)",
        # Story 5.5 — citation graph
        "ALTER TABLE articles ADD COLUMN ss_paper_id VARCHAR(64)",
        "ALTER TABLE articles ADD COLUMN cited_by_corpus_count INTEGER DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS ix_articles_ss_paper_id ON articles(ss_paper_id)",
        # Multi-tenant: organizations & users
        "CREATE TABLE IF NOT EXISTS organizations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, display_name TEXT, role TEXT NOT NULL DEFAULT 'member', org_id INTEGER REFERENCES organizations(id), onboarding_done BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "ALTER TABLE auth_sessions ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE organizations ADD COLUMN code VARCHAR(64) UNIQUE",
        # Story 2.1 — article_scores table + backfill from articles (FR-MT-7, FR-MT-12)
        """CREATE TABLE IF NOT EXISTS article_scores (user_id INTEGER NOT NULL REFERENCES users(id), article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, score FLOAT, tags_json TEXT NOT NULL DEFAULT '[]', summary_bullets_json TEXT NOT NULL DEFAULT '[]', reason VARCHAR, read_at DATETIME, bookmarked BOOLEAN NOT NULL DEFAULT 0, user_feedback INTEGER, contribution_type VARCHAR(24), re_document_type VARCHAR(24), score_meta_json TEXT, created_at DATETIME NOT NULL, PRIMARY KEY (user_id, article_id))""",
        # Story 3.1 — user_feed_subscriptions table (FR-MT-13)
        """CREATE TABLE IF NOT EXISTS user_feed_subscriptions (user_id INTEGER NOT NULL REFERENCES users(id), feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE, created_at DATETIME NOT NULL, PRIMARY KEY (user_id, feed_id))""",
        # Story 4.1 — user_config table (FR-MT-19)
        "CREATE TABLE IF NOT EXISTS user_config (user_id INTEGER PRIMARY KEY REFERENCES users(id), thesis_title TEXT NOT NULL DEFAULT '', thesis_question TEXT, thesis_contribution TEXT, thesis_sections_json TEXT NOT NULL DEFAULT '[]', scoring_clusters_json TEXT NOT NULL DEFAULT '[]', tracked_venues_json TEXT NOT NULL DEFAULT '[]', avoid_topics_json TEXT NOT NULL DEFAULT '[]', weekly_goal INTEGER NOT NULL DEFAULT 10, model_preference TEXT NOT NULL DEFAULT 'google/gemini-flash-1.5', prompt_profile TEXT NOT NULL DEFAULT 'unified', prompt_cache_text TEXT, prompt_cache_hash TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        # Story 6.5 — user_settings table (FR-MT-38)
        "CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER NOT NULL REFERENCES users(id), key TEXT NOT NULL, value TEXT NOT NULL DEFAULT '', updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, key))",
        # Story 10.1 — per-tenant facet schema (domain-agnostic generalization)
        "ALTER TABLE user_config ADD COLUMN facet_schema_json TEXT",
        # Story 10.1 — per-article facets result
        "ALTER TABLE article_scores ADD COLUMN facets_json TEXT",
        # Story 11.2 — bootstrap config fields on user_config
        "ALTER TABLE user_config ADD COLUMN thesis_text TEXT",
        "ALTER TABLE user_config ADD COLUMN domain_label VARCHAR(128)",
        "ALTER TABLE user_config ADD COLUMN bootstrap_hash VARCHAR(64)",
        "ALTER TABLE user_config ADD COLUMN bootstrap_model VARCHAR(64)",
    ]
    with engine.connect() as conn:
        for stmt in _migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists

    _seed_default_user()

    with engine.connect() as conn:
        _backfill_article_scores(conn)
        _backfill_subscriptions(conn)
        _backfill_user_config(conn)
        _backfill_research_profile(conn)
        _backfill_highlights(conn)
        _backfill_literature_reviews(conn)
        _backfill_novelty_alerts(conn)
        _backfill_tracked_authors(conn)
        _backfill_facet_schema(conn)   # Story 10.2


def _backfill_article_scores(conn):
    """Backfill existing per-article user data into article_scores for user_id=1 (single-tenant compat)."""
    try:
        conn.execute(text("""
            INSERT OR IGNORE INTO article_scores (user_id, article_id, score, tags_json, summary_bullets_json, reason, read_at, bookmarked, user_feedback, contribution_type, re_document_type, score_meta_json, created_at)
            SELECT 1, id, score, tags_json, summary_bullets_json, reason, read_at, bookmarked, user_feedback, contribution_type, re_document_type, score_meta_json, created_at
            FROM articles
        """))
        conn.commit()
    except Exception:
        pass  # table may not exist yet on very first deploy


def _backfill_subscriptions(conn):
    """Subscribe user_id=1 to all existing feeds (single-tenant compat)."""
    try:
        conn.execute(text("""
            INSERT OR IGNORE INTO user_feed_subscriptions (user_id, feed_id, created_at)
            SELECT 1, id, datetime('now') FROM feeds
        """))
        conn.commit()
    except Exception:
        pass


_DEFAULT_THESIS_SECTIONS = [
    "P1 Construction", "P2 Consistency", "P3 Model Drift",
    "P4 Trust", "P5 Blueprint Query", "Lit Review / Gap",
    "Motivation", "Related Work", "Counter-argument",
]

_DEFAULT_SCORING_CLUSTERS = [
    {"id": "A", "name": "Intrinsic CPS Complexity", "description": "Cyber-physical systems taxonomies, digital twins, structural complexity, Industry 4.0/5.0, SoS, embedded and real-time systems.", "reward_level": "high", "weight": 1.0, "tags": ["CPS", "digital twin", "Industry 4.0", "SoS", "embedded systems"], "use_as_thesis_section": False, "thesis_section_label": None},
    {"id": "B", "name": "Lifecycle & Traceability", "description": "SE standards, lifecycle-aware model management, requirements-to-model-to-code traceability, digital thread, co-evolution, change impact analysis.", "reward_level": "high", "weight": 1.0, "tags": ["ISO 15288", "digital thread", "traceability", "configuration management", "model co-evolution"], "use_as_thesis_section": False, "thesis_section_label": None},
    {"id": "C", "name": "Human & Organizational Complexity", "description": "Socio-technical SE, organizational barriers to MBSE adoption, human-in-the-loop validation, collaborative multi-stakeholder modeling.", "reward_level": "high", "weight": 1.0, "tags": ["socio-technical", "MBSE adoption", "human-in-the-loop", "collaborative modeling", "SE education"], "use_as_thesis_section": False, "thesis_section_label": None},
    {"id": "D", "name": "MBSE Adoption & Levers", "reward_level": "critical", "weight": 1.5, "description": "MBSE methodologies (SysML v1/v2, Arcadia/Capella), ROI analysis, adoption barriers, DevSecOps for SE, multi-view modeling, semantic interoperability.", "tags": ["SysML", "Capella", "MBSE methodologies", "DevSecOps", "multi-view modeling"], "use_as_thesis_section": False, "thesis_section_label": None},
    {"id": "E", "name": "AI for Systems Engineering", "reward_level": "critical", "weight": 2.0, "description": "LLM multi-agent systems for SE, NLP4RE, generative AI for model generation, hallucination mitigation, explainability of AI-generated engineering artifacts.", "tags": ["LLM for SE", "NLP4RE", "model generation", "hallucination mitigation", "XAI for SE"], "use_as_thesis_section": False, "thesis_section_label": None},
]

_DEFAULT_TRACKED_VENUES = [
    "ICSE", "RE", "MODELS", "CAiSE", "REFSQ", "ECMFA", "INCOSE", "SoSE",
    "NeurIPS", "ICLR", "EMNLP", "ACL", "NAACL", "IJCAI",
    "arXiv (cs.SE)", "arXiv (cs.AI)", "arXiv (cs.CL)", "arXiv (cs.RO)",
    "arXiv (cs.SY)", "arXiv (eess.SY)", "arXiv (cs.FL)", "arXiv (cs.MA)",
]

_DEFAULT_AVOID_TOPICS = [
    "DevOps", "Kubernetes", "Cloud infrastructure", "Cybersecurity (non-CPS)",
    "Consumer AI chatbots", "Vibe coding and productivity tools",
    "Generic Python or JS tutorials", "Marketing and startup announcements",
    "Social and political news",
]

# Story 10.2 — default CS-equivalent facet schema (mirrors legacy enums for backward compat).
_DEFAULT_FACET_SCHEMA = {
    "version": 1,
    "dimensions": [
        {
            "id": "contribution_type",
            "label": "Contribution Type",
            "type": "enum",
            "values": [
                "method", "benchmark", "survey", "empirical",
                "theory", "position", "tool", "incident",
                "tutorial", "news", "other",
            ],
        },
        {
            "id": "re_document_type",
            "label": "RE Document Type",
            "type": "enum",
            "values": ["elicitation", "extraction", "method", "none"],
        },
    ],
}


def _backfill_user_config(conn):
    """Create user_config row for user_id=1 with hardcoded defaults."""
    try:
        conn.execute(text("""
            INSERT OR IGNORE INTO user_config (
                user_id, thesis_title, thesis_question, thesis_contribution,
                thesis_sections_json, scoring_clusters_json,
                tracked_venues_json, avoid_topics_json,
                weekly_goal, model_preference, prompt_profile,
                created_at, updated_at
            ) VALUES (
                1,
                :title, :question, :contribution,
                :sections, :clusters,
                :venues, :avoids,
                10, 'google/gemini-flash-1.5', 'unified',
                datetime('now'), datetime('now')
            )
        """), {
            "title": "AI-driven model-based engineering for cyber-physical systems in the industry of the future.",
            "question": "How can AI agents be integrated into the Systems Engineering (SE) process to enable effective adoption of Model-Based Systems Engineering (MBSE) throughout the life cycle of industrial Cyber-Physical Systems (CPS)?",
            "contribution": None,
            "sections": json.dumps(_DEFAULT_THESIS_SECTIONS),
            "clusters": json.dumps(_DEFAULT_SCORING_CLUSTERS),
            "venues": json.dumps(_DEFAULT_TRACKED_VENUES),
            "avoids": json.dumps(_DEFAULT_AVOID_TOPICS),
        })
        conn.commit()
    except Exception:
        pass


def _backfill_research_profile(conn):
    """Backfill user_id=1 to existing research_profile rows."""
    try:
        conn.execute(text("UPDATE research_profile SET user_id = 1 WHERE user_id IS NULL"))
        conn.commit()
    except Exception:
        pass


def _backfill_highlights(conn):
    """Backfill user_id=1 to existing highlights."""
    try:
        conn.execute(text("UPDATE highlights SET user_id = 1 WHERE user_id IS NULL"))
        conn.commit()
    except Exception:
        pass


def _backfill_literature_reviews(conn):
    """Backfill user_id=1 to existing literature reviews."""
    try:
        conn.execute(text("UPDATE literature_reviews SET user_id = 1 WHERE user_id IS NULL"))
        conn.commit()
    except Exception:
        pass


def _backfill_novelty_alerts(conn):
    """Backfill user_id=1 to existing novelty alerts."""
    try:
        conn.execute(text("UPDATE novelty_alerts SET user_id = 1 WHERE user_id IS NULL"))
        conn.commit()
    except Exception:
        pass


def _backfill_tracked_authors(conn):
    """Backfill user_id=1 to existing tracked authors."""
    try:
        conn.execute(text("UPDATE tracked_authors SET user_id = 1 WHERE user_id IS NULL"))
        conn.commit()
    except Exception:
        pass


def _backfill_facet_schema(conn):
    """Story 10.2 — populate facet_schema_json for user_id=1 with the CS default if not yet set."""
    try:
        conn.execute(
            text(
                "UPDATE user_config SET facet_schema_json = :schema "
                "WHERE user_id = 1 AND facet_schema_json IS NULL"
            ),
            {"schema": json.dumps(_DEFAULT_FACET_SCHEMA)},
        )
        conn.commit()
    except Exception:
        pass


def get_valid_thesis_sections(db: Session, user_id: int) -> set[str]:
    """Return the user's valid thesis sections from user_config, falling back to defaults."""
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
        if config and config.thesis_sections_json:
            parsed = json.loads(config.thesis_sections_json)
            if isinstance(parsed, list) and parsed:
                return set(parsed)
    except Exception:
        pass
    return set(_DEFAULT_THESIS_SECTIONS)


def get_facet_schema(db: Session, user_id: int) -> dict:
    """Return the user's facet schema from user_config, falling back to the CS default.

    Mirrors get_valid_thesis_sections(): query UserConfig, parse JSON, fall back to
    _DEFAULT_FACET_SCHEMA on any failure (missing row, NULL column, parse error,
    non-dict payload). Never raises. Returns a dict with 'version' and 'dimensions'.
    """
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
        if config and config.facet_schema_json:
            parsed = json.loads(config.facet_schema_json)
            if isinstance(parsed, dict) and "dimensions" in parsed:
                return parsed
    except Exception:
        pass
    return _DEFAULT_FACET_SCHEMA
