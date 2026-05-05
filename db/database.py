import os
import sys
from pathlib import Path
from typing import Optional

# Load .env file
try:
    from dotenv import load_dotenv
    ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(ENV_PATH)
except ImportError:
    pass

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Lazy-loaded globals
_engine: Optional[object] = None
_SessionLocal: Optional[sessionmaker] = None


def _get_database_url() -> str:
    """Get DATABASE_URL from environment with sensible defaults."""
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        # Check if we're in a testing environment
        is_test_env = (
            "pytest" in sys.modules
            or os.environ.get("TESTING", "").lower() == "true"
        )
        if is_test_env:
            # Use in-memory SQLite for tests (will be overridden by conftest.py for real tests)
            db_url = "sqlite+aiosqlite:///:memory:"
        else:
            raise ValueError(
                "DATABASE_URL is not set in environment variables. "
                "Please set it or use .env file for local development."
            )
    
    return db_url


def get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        DATABASE_URL = _get_database_url()
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_local():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _SessionLocal


# Module-level exports for backward compatibility with imports like:
# from db.database import SessionLocal, engine
SessionLocal = get_session_local()
engine = get_engine()