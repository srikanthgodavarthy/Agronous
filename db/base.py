"""
Database engine & session management.

Connects to Supabase's managed PostgreSQL via SQLAlchemy. Supabase Auth handles
user identity (auth.users); our application tables live in the `public` schema
and reference auth.users.id as a plain UUID foreign key (Supabase's recommended
pattern), enforced additionally with Row Level Security policies at the DB level.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def get_database_url() -> str:
    """
    Resolve the database URL.

    Prefers the explicit DATABASE_URL (recommended: Supabase's "connection
    pooling" URI on port 6543 for serverless-friendly, short-lived
    connections from a Streamlit app). Falls back to st.secrets if running
    inside Streamlit and the env var isn't set.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st  # local import: keep db layer importable w/o streamlit

        return st.secrets["DATABASE_URL"]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "DATABASE_URL not found in environment or st.secrets. "
            "Set it to your Supabase Postgres connection string."
        ) from exc


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, class_=Session)
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
