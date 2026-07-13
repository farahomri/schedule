import os
import re
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _resolve_database_url() -> str:
    """
    Resolve DATABASE_URL from (in priority order):
      1. Environment variable DATABASE_URL
      2. st.secrets["DATABASE_URL"]  (Streamlit Cloud)
      3. st.secrets["connections"]["postgresql"]["url"]  (Streamlit connection syntax)
    Raises RuntimeError if none found.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL")
        if url:
            return url
        # Streamlit connection block: [connections.postgresql] url = "..."
        url = st.secrets.get("connections", {}).get("postgresql", {}).get("url")
        if url:
            return url
    except Exception:
        pass

    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it to your environment variables or to .streamlit/secrets.toml as:\n"
        "    DATABASE_URL = \"postgresql://user:pass@host:5432/dbname\""
    )


def _build_engine():
    url = _resolve_database_url()
    # Normalise to psycopg2 driver — we ship psycopg2-binary, not psycopg3.
    url = re.sub(r"^postgresql(\+psycopg)?://", "postgresql+psycopg2://", url)
    return create_engine(url, pool_pre_ping=True)


# Engine and session factory are created lazily on first use,
# so importing this module never fails even when DATABASE_URL isn't set yet.
_engine = None
_session_factory = None


def _get_session_factory():
    global _engine, _session_factory
    if _session_factory is None:
        _engine = _build_engine()
        _session_factory = sessionmaker(bind=_engine)
    return _session_factory


@contextmanager
def get_session():
    """Yield a SQLAlchemy session. Commits on success, rolls back on exception."""
    session: Session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
