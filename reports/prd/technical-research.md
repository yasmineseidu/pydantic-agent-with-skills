# Technical Research: Phase 1 - Database Foundation
Status: COMPLETE

## Existing Codebase Scan

### Import Graph (src/)
```
settings.py         -> (no src imports)
providers.py        -> settings
skill_loader.py     -> (no src imports)
prompts.py          -> (no src imports)
skill_tools.py      -> dependencies (TYPE_CHECKING only)
skill_toolset.py    -> dependencies, skill_tools
dependencies.py     -> skill_loader, settings
agent.py            -> providers, dependencies, prompts, skill_toolset, http_tools, settings
cli.py              -> agent, dependencies, settings
```

### Key Patterns to Follow
1. **Module logger**: `logger = logging.getLogger(__name__)` at module top
2. **Structured logging**: `f"action_name: key={value}"` format
3. **Pydantic models**: `BaseModel` with `Field()` for validation (see SkillMetadata)
4. **Settings**: `BaseSettings` with ConfigDict, `load_settings()` factory
5. **Dependencies**: `@dataclass AgentDependencies` with `async initialize()`
6. **TYPE_CHECKING**: Used in `skill_tools.py` to avoid circular imports
7. **Error returns**: Tool functions return `f"Error: {msg}"` strings, don't raise
8. **Google docstrings**: Args/Returns/Raises on all public functions
9. **Import style**: `from src.module import Class` (absolute, never relative)

### Files to Modify (Phase 1)
| File | Change Type | Impact |
|------|-------------|--------|
| `src/settings.py` | Add 6 Optional fields | None -- all have defaults |
| `pyproject.toml` | Add 4 dependencies | None -- additive |
| `.env.example` | Add 3 placeholder lines | None -- additive |

### Files to Create (Phase 1)
```
src/db/__init__.py
src/db/engine.py
src/db/base.py
src/db/models/__init__.py
src/db/models/user.py
src/db/models/agent.py
src/db/models/conversation.py
src/db/models/memory.py
src/models/__init__.py
src/models/agent_models.py
src/models/memory_models.py
src/models/conversation_models.py
src/models/user_models.py
src/db/repositories/__init__.py
src/db/repositories/base.py
src/db/repositories/memory_repo.py
alembic.ini
src/db/migrations/env.py
src/db/migrations/script.py.mako
src/db/migrations/versions/.gitkeep
tests/test_db/__init__.py
tests/test_db/conftest.py
tests/test_db/test_engine.py
tests/test_db/test_models.py
tests/test_db/test_repositories.py
tests/test_models/__init__.py
tests/test_models/test_agent_models.py
tests/test_models/test_memory_models.py
```

---

## SQLAlchemy 2.0 Async Patterns

### Engine + Session Factory
```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)

async def create_engine(database_url: str, pool_size: int = 5, max_overflow: int = 10) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=False,  # Set True for SQL debugging
    )

def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
```

### Declarative Base (SQLAlchemy 2.0 style)
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, MappedAsDataclass
from sqlalchemy import DateTime, func, text
from uuid import UUID
from datetime import datetime

class Base(DeclarativeBase):
    pass

class UUIDMixin:
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
```

### ENUM Handling in SQLAlchemy 2.0
```python
import enum
from sqlalchemy import Enum as SAEnum

class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

# In model:
role: Mapped[UserRole] = mapped_column(
    SAEnum(UserRole, name="user_role", create_constraint=False, native_enum=True),
    nullable=False,
    server_default="member",
)
```

### pgvector Integration
```python
from pgvector.sqlalchemy import Vector

# In model:
embedding: Mapped[Optional[list[float]]] = mapped_column(
    Vector(1536),
    nullable=True,
)
```

### JSONB Columns
```python
from sqlalchemy import JSON

personality: Mapped[dict] = mapped_column(
    JSON,
    nullable=False,
    server_default="{}",
)
```

### ARRAY Columns
```python
from sqlalchemy import ARRAY, Text

shared_skill_names: Mapped[list[str]] = mapped_column(
    ARRAY(Text),
    nullable=False,
    server_default="{}",
)
```

### Self-Referential FK
```python
superseded_by: Mapped[Optional[UUID]] = mapped_column(
    ForeignKey("memory.id"),
    nullable=True,
)
```

### Relationship Patterns
```python
from sqlalchemy.orm import relationship

class Team(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "team"

    owner_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=False)

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="owned_teams")
    memberships: Mapped[list["TeamMembership"]] = relationship(back_populates="team")
    agents: Mapped[list["Agent"]] = relationship(back_populates="team")
```

---

## Alembic Async Setup

### alembic.ini
```ini
[alembic]
script_location = src/db/migrations
sqlalchemy.url = postgresql+asyncpg://user:pass@localhost/dbname
# Overridden by env.py to use Settings

[loggers]
keys = root,sqlalchemy,alembic
```

### env.py (Async)
```python
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import Base so Alembic discovers all models
from src.db.base import Base
from src.db.models import *  # noqa: F403 - force model import for Alembic
from src.settings import load_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    settings = load_settings()
    configuration = config.get_section(config.config_ini_section, {})
    if settings.database_url:
        configuration["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Migration Strategy
- Single initial migration for all 9 Phase 1 tables
- Migration creates extensions, enums, tables, indexes, functions, triggers in order
- Downgrade drops triggers, functions, indexes, tables, enums (reverse order)
- Extensions are NOT dropped on downgrade (shared resource)

---

## pgvector Integration

### Requirements
- PostgreSQL with `vector` extension installed
- `pgvector~=0.3.6` Python package
- SQLAlchemy adapter via `pgvector.sqlalchemy.Vector`

### Index Creation
```python
from sqlalchemy import Index, text

# IVFFlat index for cosine similarity
Index(
    "idx_memory_embedding",
    MemoryORM.embedding,
    postgresql_using="ivfflat",
    postgresql_with={"lists": 100},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
```

### Vector Search Query
```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import select, func

# Cosine similarity search
stmt = (
    select(MemoryORM)
    .where(
        MemoryORM.team_id == team_id,
        MemoryORM.status == "active",
        MemoryORM.embedding.isnot(None),
    )
    .order_by(MemoryORM.embedding.cosine_distance(query_embedding))
    .limit(limit)
)
```

---

## Repository Pattern

### Base Repository (Generic CRUD)
```python
from typing import TypeVar, Generic, Optional, Type
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model_class: Type[T]) -> None:
        self._session = session
        self._model_class = model_class

    async def get_by_id(self, id: UUID) -> Optional[T]:
        return await self._session.get(self._model_class, id)

    async def create(self, **kwargs) -> T:
        instance = self._model_class(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def update(self, id: UUID, **kwargs) -> Optional[T]:
        instance = await self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self._session.flush()
        return instance

    async def delete(self, id: UUID) -> bool:
        instance = await self.get_by_id(id)
        if instance:
            await self._session.delete(instance)
            await self._session.flush()
            return True
        return False
```

### Memory Repository (Specialized)
```python
class MemoryRepository(BaseRepository[MemoryORM]):
    async def search_by_embedding(
        self,
        embedding: list[float],
        team_id: UUID,
        agent_id: Optional[UUID] = None,
        memory_types: Optional[list[MemoryType]] = None,
        limit: int = 20,
    ) -> list[MemoryORM]:
        stmt = (
            select(MemoryORM)
            .where(
                MemoryORM.team_id == team_id,
                MemoryORM.status == MemoryStatus.ACTIVE,
                MemoryORM.embedding.isnot(None),
            )
        )
        if agent_id:
            stmt = stmt.where(MemoryORM.agent_id == agent_id)
        if memory_types:
            stmt = stmt.where(MemoryORM.memory_type.in_(memory_types))

        stmt = stmt.order_by(
            MemoryORM.embedding.cosine_distance(embedding)
        ).limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

---

## Testing Strategy

### Pydantic Model Tests (No DB needed)
- Pure unit tests validating model creation, defaults, constraints, computed fields
- Uses `pytest` (no async needed for Pydantic models)
- Example: `AgentDNA.effective_skills` property, `RetrievalWeights` defaults

### ORM Model Tests (Requires DB)
- Test that ORM models can be instantiated and relationships resolve
- Two options:
  1. **SQLite in-memory** (fast, limited -- no pgvector, no PG-specific features)
  2. **Test PostgreSQL** (slower, full fidelity -- requires running PG with pgvector)
- Recommendation: Use pytest fixtures with `@pytest.mark.skipif` for PG-dependent tests
- Mark DB tests with `@pytest.mark.integration`

### Repository Tests (Requires DB)
- Integration tests using a test PostgreSQL database
- Fixtures: create engine, run migrations, provide session, rollback after each test
- Mark with `@pytest.mark.integration`

### Fixture Pattern
```python
@pytest.fixture
async def db_engine():
    """Create async engine for test database."""
    settings = load_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(settings.database_url)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    """Create transactional session for test isolation."""
    async_session = async_sessionmaker(db_engine, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()
```

---

## Dependency Pinning

### Recommended Versions (compatible release)
```toml
"sqlalchemy[asyncio]~=2.0.36"  # SQLAlchemy 2.0 with async support
"asyncpg~=0.30.0"              # PostgreSQL async driver
"alembic~=1.14.0"              # Migration framework
"pgvector~=0.3.6"              # pgvector SQLAlchemy adapter
```

### Why `~=` (Compatible Release)
- `~=2.0.36` allows `2.0.37`, `2.0.38`, etc. but NOT `2.1.0`
- Prevents unexpected breaking changes from minor/major bumps
- Follows the phase doc specification

---

## Integration Risk Assessment

| Integration Point | Risk | Mitigation |
|-------------------|------|------------|
| settings.py modification | LOW | All new fields are Optional with defaults |
| pyproject.toml deps | LOW | New deps don't conflict with existing |
| .env.example | LOW | Additive only, no existing lines changed |
| Import of src.db in future phases | NONE | Phase 1 creates modules but nothing imports them yet |
| CLI backward compat | LOW | Settings defaults ensure CLI works without DB |
| Test isolation | MEDIUM | DB tests marked @pytest.mark.integration, skipped without DATABASE_URL |
