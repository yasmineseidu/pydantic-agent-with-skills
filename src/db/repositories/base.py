"""Base repository with generic CRUD operations."""

from typing import Generic, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations.

    Provides get_by_id, create, update, delete, and list_all operations
    for any SQLAlchemy ORM model. Transaction control is left to the caller;
    this repository uses flush() + refresh() rather than commit().

    Args:
        session: AsyncSession for database operations.
        model_class: The ORM model class this repository manages.
    """

    def __init__(self, session: AsyncSession, model_class: Type[T]) -> None:
        self._session = session
        self._model_class = model_class

    async def get_by_id(self, id: UUID) -> Optional[T]:
        """Get a single record by ID.

        Args:
            id: UUID of the record.

        Returns:
            The record if found, None otherwise.
        """
        return await self._session.get(self._model_class, id)

    async def create(self, **kwargs: object) -> T:
        """Create a new record.

        Args:
            **kwargs: Field values for the new record.

        Returns:
            The created record with server-generated fields populated.
        """
        instance = self._model_class(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def update(self, id: UUID, **kwargs: object) -> Optional[T]:
        """Update an existing record.

        Args:
            id: UUID of the record to update.
            **kwargs: Fields to update.

        Returns:
            The updated record if found, None otherwise.
        """
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, id: UUID) -> bool:
        """Delete a record by ID.

        Args:
            id: UUID of the record to delete.

        Returns:
            True if deleted, False if not found.
        """
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self._session.delete(instance)
        await self._session.flush()
        return True

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """List records with pagination.

        Args:
            limit: Max records to return.
            offset: Number of records to skip.

        Returns:
            List of records.
        """
        stmt = select(self._model_class).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
