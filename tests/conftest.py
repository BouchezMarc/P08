"""Pytest configuration and fixtures for testing."""

import os
import pytest

# CRITICAL: Set test database URL BEFORE any imports
# Use in-memory SQLite for unit tests (fast, isolated, no external dependencies)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TESTING"] = "true"


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Setup test database connection before running tests.
    This fixture ensures DATABASE_URL is set in all test scenarios.
    """
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["TESTING"] = "true"
    yield
    # Cleanup after tests
    os.environ.pop("TESTING", None)


@pytest.fixture
def test_env():
    """Fixture to ensure test environment variables are set for individual tests."""
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    yield
    if original_db_url:
        os.environ["DATABASE_URL"] = original_db_url
    else:
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for async tests."""
    return "asyncio"
