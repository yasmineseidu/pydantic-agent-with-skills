"""SQLAlchemy declarative base and common mixins."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models.

    All ORM models in this project should inherit from this base class.
    Provides automatic table name generation and metadata registry.
    """

    pass


class UUIDMixin:
    """Mixin providing a UUID primary key.

    Adds an ``id`` column as a UUID primary key with auto-generated uuid4 default.
    Inherit alongside Base to add a UUID primary key to any model.
    """

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamps.

    Adds ``created_at`` and ``updated_at`` columns with timezone-aware datetimes.
    Both default to the database server's current time. ``updated_at`` also
    refreshes on every row update via ``onupdate``.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
