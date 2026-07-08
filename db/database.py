import os
import re
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _build_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it in your environment or .streamlit/secrets.toml."
        )
    # Normalise to psycopg2 — we ship psycopg2-binary, not psycopg3.
    # Handles: postgresql://, postgresql+psycopg://, postgresql+psycopg2://
    url = re.sub(r"^postgresql(\+psycopg)?://", "postgresql+psycopg2://", url)
    return create_engine(url, pool_pre_ping=True)


engine = _build_engine()
SessionFactory = sessionmaker(bind=engine)


@contextmanager
def get_session():
    """Yield a SQLAlchemy session. Commits on success, rolls back on exception."""
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
