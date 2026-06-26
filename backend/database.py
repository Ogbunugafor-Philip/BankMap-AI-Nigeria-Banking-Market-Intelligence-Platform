"""
database.py — PostgreSQL + PostGIS connection layer for BankMap AI.

Responsibilities:
  * Read credentials from the project .env (never hardcoded).
  * Build a SQLAlchemy engine / session factory.
  * Provide helpers to enable the PostGIS extension and create all tables.

GeoAlchemy2 is imported by models.py to give SQLAlchemy spatial column support;
the engine here speaks to a PostGIS-enabled PostgreSQL database.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# Load environment. We look for a .env at the project root (one level above
# the backend/ folder) and also fall back to the default search behaviour.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
load_dotenv()  # fall back to any .env on the default path as well


def _build_database_url() -> str:
    """
    Prefer a full DATABASE_URL. If it is absent, assemble one from the
    individual DB_* parts. Credentials always come from the environment.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "bankmap")
    user = os.getenv("DB_USER", "username")
    password = os.getenv("DB_PASSWORD", "password")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = _build_database_url()

# pool_pre_ping avoids stale-connection errors after the DB idles.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# Session factory used by routers and loader scripts.
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# Declarative base shared by every model.
Base = declarative_base()


def enable_postgis() -> None:
    """Enable the PostGIS extension (idempotent — uses IF NOT EXISTS)."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
    print("[database] PostGIS extension ensured.")


def init_db() -> None:
    """
    Enable PostGIS then create all tables defined on Base.metadata.
    Importing models here guarantees every table is registered before
    create_all runs. Safe to call repeatedly.
    """
    enable_postgis()
    import models  # noqa: F401  (import side effect registers the tables)

    Base.metadata.create_all(bind=engine)
    print("[database] All tables created / verified.")


def get_db():
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    # Running `python database.py` bootstraps the schema.
    init_db()
