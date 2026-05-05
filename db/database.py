import os
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(ENV_PATH)
except ImportError:
    print("Warning: python-dotenv not installed")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables")

# Engine async
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)