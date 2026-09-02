from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def create_engine_from_url(url: str, **kwargs) -> Engine:
    return create_engine(normalize_database_url(url), pool_pre_ping=True, **kwargs)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def database_url_from_env() -> str | None:
    return os.getenv("LOREX_DATABASE_URL")
