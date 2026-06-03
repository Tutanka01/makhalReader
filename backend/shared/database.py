"""
Shared database initialization module for Baṣīra.
This module provides the SQLAlchemy engine, session factory, and ORM models
shared across backend services. Each service can import from here.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime

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


class AuthSession(Base):
    """Persistent login sessions. One row per active login."""
    __tablename__ = "auth_sessions"

    id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    last_seen = Column(DateTime, nullable=True)
    user_agent = Column(String(500), nullable=True)
    remember_me = Column(Boolean, default=False, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    user_feedback = Column(Integer, nullable=True)  # 1=like, -1=dislike, NULL=no feedback
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Deduplication fingerprints — nullable for backwards compatibility with
    # articles ingested before this column was introduced.
    title_fingerprint = Column(String(16), nullable=True, index=True)

    # Research-dimension columns — nullable; populated by scorer after Story 2.1.
    score_meta_json = Column(Text, nullable=True)
    contribution_type = Column(String(24), nullable=True)
    re_document_type = Column(String(24), nullable=True)

    # Paper enrichment — populated by poller before scoring (Story 2.2).
    paper_meta_json = Column(Text, nullable=True)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserFeedSubscription(Base):
    """User-to-feed subscription (Story 3.1, FR-MT-13)."""
    __tablename__ = "user_feed_subscriptions"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    feed_id = Column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Add columns introduced after the initial schema creation (SQLite-safe migrations).
    _migrations = [
        "ALTER TABLE articles ADD COLUMN title_fingerprint VARCHAR(16)",
        "ALTER TABLE articles ADD COLUMN score_meta_json TEXT",
        "ALTER TABLE articles ADD COLUMN re_document_type VARCHAR(24)",
        "ALTER TABLE articles ADD COLUMN contribution_type VARCHAR(24)",
        "ALTER TABLE articles ADD COLUMN paper_meta_json TEXT",
        # Auth sessions table + user_id column
        "CREATE TABLE IF NOT EXISTS auth_sessions (id VARCHAR(64) PRIMARY KEY, created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, last_seen DATETIME, user_agent VARCHAR(500), remember_me BOOLEAN NOT NULL DEFAULT 0, user_id INTEGER REFERENCES users(id))",
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires_at ON auth_sessions(expires_at)",
        # Multi-tenant: organizations & users
        "CREATE TABLE IF NOT EXISTS organizations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, display_name TEXT, role TEXT NOT NULL DEFAULT 'member', org_id INTEGER REFERENCES organizations(id), onboarding_done BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "ALTER TABLE auth_sessions ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE organizations ADD COLUMN code VARCHAR(64) UNIQUE",
        # Story 2.1 — article_scores table + backfill from articles (FR-MT-7, FR-MT-12)
        "CREATE TABLE IF NOT EXISTS article_scores (user_id INTEGER NOT NULL REFERENCES users(id), article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, score FLOAT, tags_json TEXT NOT NULL DEFAULT '[]', summary_bullets_json TEXT NOT NULL DEFAULT '[]', reason VARCHAR, read_at DATETIME, bookmarked BOOLEAN NOT NULL DEFAULT 0, user_feedback INTEGER, contribution_type VARCHAR(24), re_document_type VARCHAR(24), score_meta_json TEXT, created_at DATETIME NOT NULL, PRIMARY KEY (user_id, article_id))",
        # Story 3.1 — user_feed_subscriptions table (FR-MT-13)
        "CREATE TABLE IF NOT EXISTS user_feed_subscriptions (user_id INTEGER NOT NULL REFERENCES users(id), feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE, created_at DATETIME NOT NULL, PRIMARY KEY (user_id, feed_id))",
    ]
    with engine.connect() as conn:
        for stmt in _migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists — idempotent

        _backfill_article_scores(conn)
        _backfill_subscriptions(conn)

    _seed_default_user()


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


def _seed_default_user():
    """Auto-create seed user_id=1 when AUTH_PASSWORD is set and users table is empty."""
    raw = os.getenv("AUTH_PASSWORD", "")
    if not raw:
        return
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
