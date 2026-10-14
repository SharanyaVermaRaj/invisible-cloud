"""Database setup. SQLite locally, Postgres in production (set DATABASE_URL)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import database_url


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None, **kwargs):
    url = url or database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if not url.startswith("sqlite"):
        kwargs.setdefault("pool_pre_ping", True)
    return create_engine(url, connect_args=connect_args, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
