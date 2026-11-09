"""
Gestión de sesión asíncrona de PostgreSQL con SQLAlchemy 2.0 (asyncpg).
Provee la clase declarativa Base y el inyector de dependencias get_db.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos de persistencia SQLAlchemy 2.0."""
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Inyector de dependencia para proveer una sesión de base de datos asíncrona por petición.
    Garantiza el cierre seguro de la conexión al finalizar el contexto.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

