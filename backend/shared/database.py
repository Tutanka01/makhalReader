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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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
    ]
    with engine.connect() as conn:
        for stmt in _migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists — idempotent

    _seed_default_user()


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
