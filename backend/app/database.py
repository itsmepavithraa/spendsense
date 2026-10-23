"""Database connection setup (SQLAlchemy engine, session factory, base class)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# The engine is the connection pool to Postgres; pool_pre_ping drops dead connections.
engine = create_engine(settings.database_url, pool_pre_ping=True)
# A session is a workspace where we add / query / commit objects.
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """All models inherit from this; Alembic reads its metadata."""


def get_db():
    """FastAPI dependency: one DB session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
