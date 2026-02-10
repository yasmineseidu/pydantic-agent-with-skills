"""Fixtures for database model tests."""

import pytest

from src.db.base import Base

# Force all models to register with Base.metadata
import src.db.models  # noqa: F401


@pytest.fixture
def all_tables() -> set[str]:
    """Get all table names from Base metadata."""
    return set(Base.metadata.tables.keys())
